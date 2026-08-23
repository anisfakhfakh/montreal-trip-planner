"""Flask entry point: HTTP routes, in-memory caches (BIXI/weather/construction/events/live
vehicles, each with its own TTL), and startup wiring for the transit schedule + walk/bike graph.
Routing/scoring logic itself lives in engine/ (see engine/README.md); this file's job is request
handling, caching, and gluing engine/services together, see ARCHITECTURE.md for the full
request lifecycle."""
import time
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

import requests
from flask import Flask, jsonify, render_template, request

from config import Config
from engine.data_refresh import get_status, start_bixi_refresh, start_stm_refresh
from engine.graph_builder import build_transit_data
from engine.router import GeoPointIndex, estimate_live_vehicle, next_departures_for_leg, plan_trip_alternatives, reroute_bike_leg
from engine.walk_graph import load_walk_graph
from engine.weather import classify_harsh_weather
from engine.weights_config import (
    BIXI_ACCESS_RADIUS_M,
    BIXI_FEW_THRESHOLD,
    BIXI_PLENTY_THRESHOLD,
    MAP_BOUNDS_PADDING_M,
    METRO_BLUE_LINE_DISPLAY_COLOR,
    METRO_BLUE_LINE_REAL_COLOR,
    REM_LINE_COLOR,
    ROUTE_TYPE_METRO,
    ROUTE_TYPE_REM,
)
from services.bixi_client import fetch_bixi_stations
from services.construction_client import fetch_construction_closures
from services.construction_client import is_active_at as is_closure_active_at
from services.events_client import fetch_events
from services.events_client import is_active_at as is_event_active_at
from services.geocode_client import geocode
from services.stm_client import fetch_stm_trip_updates, fetch_stm_vehicle_positions
from services.weather_client import fetch_current_weather

Config.validate()

app = Flask(__name__)

transit_data = build_transit_data()
walk_graph = load_walk_graph()

_bixi_cache = {"stations": None, "fetched_at": 0}
BIXI_CACHE_TTL_SEC = 30
_weather_cache = {"data": None, "fetched_at": 0}
WEATHER_CACHE_TTL_SEC = 900
_construction_cache = {"closures": None, "fetched_at": 0}
_events_cache = {"events": None, "fetched_at": 0}
DAILY_DATASET_CACHE_TTL_SEC = 6 * 3600  # source data only updates once a day
_live_vehicles_cache = {"positions": None, "trip_updates": None, "fetched_at": 0}
LIVE_VEHICLES_CACHE_TTL_SEC = 30  # matches the frontend's own poll interval
EARTH_RADIUS_M = 6371000


def get_bixi_stations():
    if _bixi_cache["stations"] is None or time.time() - _bixi_cache["fetched_at"] > BIXI_CACHE_TTL_SEC:
        _bixi_cache["stations"] = fetch_bixi_stations()
        _bixi_cache["fetched_at"] = time.time()
    return _bixi_cache["stations"]


def get_live_vehicles():
    if _live_vehicles_cache["positions"] is None or time.time() - _live_vehicles_cache["fetched_at"] > LIVE_VEHICLES_CACHE_TTL_SEC:
        _live_vehicles_cache["positions"] = fetch_stm_vehicle_positions()
        _live_vehicles_cache["trip_updates"] = fetch_stm_trip_updates()
        _live_vehicles_cache["fetched_at"] = time.time()
    return _live_vehicles_cache["positions"], _live_vehicles_cache["trip_updates"]


def get_weather():
    if _weather_cache["data"] is None or time.time() - _weather_cache["fetched_at"] > WEATHER_CACHE_TTL_SEC:
        _weather_cache["data"] = fetch_current_weather()
        _weather_cache["fetched_at"] = time.time()
    return _weather_cache["data"]


def get_construction_closures():
    if _construction_cache["closures"] is None or time.time() - _construction_cache["fetched_at"] > DAILY_DATASET_CACHE_TTL_SEC:
        _construction_cache["closures"] = fetch_construction_closures()
        _construction_cache["fetched_at"] = time.time()
    return _construction_cache["closures"]


def get_events():
    if _events_cache["events"] is None or time.time() - _events_cache["fetched_at"] > DAILY_DATASET_CACHE_TTL_SEC:
        _events_cache["events"] = fetch_events()
        _events_cache["fetched_at"] = time.time()
    return _events_cache["events"]


def bixi_availability_level(bikes_available):
    if bikes_available >= BIXI_PLENTY_THRESHOLD:
        return "plenty"
    if bikes_available >= BIXI_FEW_THRESHOLD:
        return "few"
    return "empty"


def _haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def _build_metro_stations():
    stations = []
    for stop_id, (name, lat, lon) in transit_data.stops.items():
        lines = []
        for route_id in transit_data.stop_routes.get(stop_id, ()):
            short_name, _, route_color, _, route_type = transit_data.routes[route_id]
            if route_type not in (ROUTE_TYPE_METRO, ROUTE_TYPE_REM):
                continue
            if route_type == ROUTE_TYPE_REM:
                color = REM_LINE_COLOR
            elif route_type == ROUTE_TYPE_METRO and route_color == METRO_BLUE_LINE_REAL_COLOR:
                color = METRO_BLUE_LINE_DISPLAY_COLOR
            else:
                color = route_color or "000000"
            lines.append({"route_short_name": short_name, "route_type": route_type, "color": color})
        if not lines:
            continue
        lines.sort(key=lambda l: l["route_short_name"])
        stations.append({
            "id": stop_id, "name": name, "lat": lat, "lon": lon,
            "color": lines[0]["color"], "lines": lines,
        })
    return stations


_metro_stations_cache = _build_metro_stations()


def _build_map_bounds():
    lats = [s["lat"] for s in _metro_stations_cache]
    lons = [s["lon"] for s in _metro_stations_cache]
    try:
        for s in get_bixi_stations().values():
            lats.append(s["lat"])
            lons.append(s["lon"])
    except requests.RequestException:
        pass  # metro/REM-only bounds are still a reasonable degrade if BIXI is down at startup
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_pad = MAP_BOUNDS_PADDING_M / 111_320
    lon_pad = MAP_BOUNDS_PADDING_M / (111_320 * cos(radians((min_lat + max_lat) / 2)))
    return {
        "south": min_lat - lat_pad, "north": max_lat + lat_pad,
        "west": min_lon - lon_pad, "east": max_lon + lon_pad,
    }


_map_bounds_cache = _build_map_bounds()


def _reload_walk_graph():
    """on_success callback for the BIXI refresh job, runs in the job's own worker thread
    after the precompute subprocess exits 0, so the freshly rebuilt walk_graph_cache.pkl (new
    BIXI stations, new neighbor/edge cache) takes effect without restarting the app. Simple
    global reassignment is safe here without extra locking: CPython's GIL makes a bare name
    rebind atomic, so a concurrent request sees either the old or the new object, never a torn
    one."""
    global walk_graph
    walk_graph = load_walk_graph()


def _reload_transit_data():
    """Same idea as _reload_walk_graph, for the STM refresh job, also rebuilds the two
    caches that are derived from transit_data at startup (metro station list, map bounds),
    since a schedule refresh could in principle add/remove/move a station."""
    global transit_data, _metro_stations_cache, _map_bounds_cache
    transit_data = build_transit_data()
    _metro_stations_cache = _build_metro_stations()
    _map_bounds_cache = _build_map_bounds()


@app.route("/api/admin/refresh/<job>", methods=["POST"])
def api_admin_refresh(job):
    if job == "bixi":
        started = start_bixi_refresh(on_success=_reload_walk_graph)
    elif job == "stm":
        started = start_stm_refresh(on_success=_reload_transit_data)
    else:
        return jsonify({"error": "unknown refresh job"}), 404
    if not started:
        return jsonify({"error": "already running"}), 409
    return jsonify({"status": "started"})


@app.route("/api/admin/refresh_status")
def api_admin_refresh_status():
    return jsonify({"bixi": get_status("bixi"), "stm": get_status("stm")})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/bixi_stations")
def api_bixi_stations():
    stations = get_bixi_stations()
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    radius = request.args.get("radius", type=float, default=BIXI_ACCESS_RADIUS_M)

    items = stations.items()
    if lat is not None and lon is not None:
        items = [(sid, s) for sid, s in items if _haversine_m(lat, lon, s["lat"], s["lon"]) <= radius]

    return jsonify([
        {
            "id": station_id,
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "bikes_available": s["bikes_available"],
            "classic_bikes_available": max(s["bikes_available"] - s.get("ebikes_available", 0), 0),
            "ebikes_available": s.get("ebikes_available", 0),
            "docks_available": s["docks_available"],
            "level": bixi_availability_level(s["bikes_available"]),
        }
        for station_id, s in items
    ])


@app.route("/api/metro_stations")
def api_metro_stations():
    return jsonify(_metro_stations_cache)


@app.route("/api/map_bounds")
def api_map_bounds():
    return jsonify(_map_bounds_cache)


@app.route("/api/construction")
def api_construction():
    closures = get_construction_closures()
    now = datetime.now()
    active = [c for c in closures if is_closure_active_at(c, now)]

    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    radius = request.args.get("radius", type=float)
    if lat is not None and lon is not None and radius is not None:
        active = [c for c in active if _haversine_m(lat, lon, c["lat"], c["lon"]) <= radius]

    return jsonify(active)


@app.route("/api/events")
def api_events():
    events = get_events()
    now = datetime.now()
    active = [e for e in events if is_event_active_at(e, now)]

    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    radius = request.args.get("radius", type=float)
    if lat is not None and lon is not None and radius is not None:
        active = [e for e in active if _haversine_m(lat, lon, e["lat"], e["lon"]) <= radius]

    return jsonify(active)


@app.route("/api/geocode")
def api_geocode():
    query = request.args.get("q", "").strip()
    if len(query) < 3:
        return jsonify([])
    b = _map_bounds_cache
    viewbox = f"{b['west']},{b['north']},{b['east']},{b['south']}"
    try:
        results = geocode(query, viewbox=viewbox)
    except requests.RequestException:
        return jsonify({"error": "geocoding service unavailable"}), 502
    return jsonify(results)


@app.route("/api/plan_trip", methods=["POST"])
def api_plan_trip():
    body = request.get_json(silent=True) or {}
    origin = body.get("origin")
    destination = body.get("destination")

    if not origin or not destination:
        return jsonify({"error": "origin and destination are both required"}), 400
    try:
        origin = {"lat": float(origin["lat"]), "lon": float(origin["lon"])}
        destination = {"lat": float(destination["lat"]), "lon": float(destination["lon"])}
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "origin and destination must have numeric lat/lon"}), 400

    allow_ebike = bool(body.get("allow_ebike", False))
    departure_time = body.get("departure_time")
    departure_dt = datetime.fromisoformat(departure_time) if departure_time else datetime.now()

    raw_modes = body.get("modes")
    modes = {key: bool(raw_modes[key]) for key in ("bus", "metro", "rem", "bixi") if isinstance(raw_modes, dict) and key in raw_modes}
    if isinstance(raw_modes, dict) and raw_modes.get("max_walk_minutes") is not None:
        try:
            modes["max_walk_minutes"] = float(raw_modes["max_walk_minutes"])
        except (TypeError, ValueError):
            pass

    bixi_stations = get_bixi_stations()
    active_closures = [c for c in get_construction_closures() if is_closure_active_at(c, departure_dt)]
    active_events = [e for e in get_events() if is_event_active_at(e, departure_dt)]

    itineraries = plan_trip_alternatives(
        transit_data, bixi_stations, walk_graph, origin, destination, departure_dt,
        allow_ebike=allow_ebike, modes=modes, active_closures=active_closures, active_events=active_events,
    )

    if not itineraries:
        return jsonify({"error": "no route found between these points"}), 404

    return jsonify({"itineraries": itineraries, "weather": classify_harsh_weather(get_weather())})


@app.route("/api/next_departures", methods=["POST"])
def api_next_departures():
    body = request.get_json(silent=True) or {}
    route_id = body.get("route_id")
    from_stop = body.get("from_stop")
    to_stop = body.get("to_stop")
    if not route_id or not from_stop or not to_stop:
        return jsonify({"error": "route_id, from_stop, and to_stop are required"}), 400

    departure_time = body.get("departure_time")
    reference_dt = datetime.fromisoformat(departure_time) if departure_time else datetime.now()
    active_today = transit_data.active_service_ids(reference_dt.date())
    active_yesterday = transit_data.active_service_ids(reference_dt.date() - timedelta(days=1))
    after_sec = reference_dt.hour * 3600 + reference_dt.minute * 60 + reference_dt.second

    departures = next_departures_for_leg(
        transit_data, route_id, from_stop, to_stop, after_sec, active_today, active_yesterday,
    )

    # Prefer STM's live, delay-adjusted prediction over the static schedule time when this
    # specific upcoming run is already being tracked in realtime, buses only, since STM's
    # feed doesn't cover metro and REM's live feed isn't wired up. Static schedule stays the
    # fallback for every other case (metro/REM legs, or a bus too far out to be in the feed yet).
    _, live_trip_updates = get_live_vehicles()
    for dep in departures:
        live_times = live_trip_updates.get(dep["trip_id"], {})
        live_dep_unix = live_times.get(from_stop)
        live_arr_unix = live_times.get(to_stop)
        dep["live"] = live_dep_unix is not None
        if live_dep_unix is not None:
            live_dt = datetime.fromtimestamp(live_dep_unix)
            dep["dep_sec"] = live_dt.hour * 3600 + live_dt.minute * 60 + live_dt.second
        if live_arr_unix is not None:
            live_dt = datetime.fromtimestamp(live_arr_unix)
            dep["arr_sec"] = live_dt.hour * 3600 + live_dt.minute * 60 + live_dt.second
        del dep["trip_id"]

    return jsonify({"departures": departures})


@app.route("/api/live_vehicles", methods=["POST"])
def api_live_vehicles():
    body = request.get_json(silent=True) or {}
    trip_ids = body.get("trip_ids")
    if not isinstance(trip_ids, list) or not trip_ids:
        return jsonify({"error": "trip_ids (a non-empty list) is required"}), 400

    live_gps, live_trip_updates = get_live_vehicles()
    now = datetime.now()
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    now_unix = int(now.timestamp())

    vehicles = []
    for trip_id in trip_ids:
        result = estimate_live_vehicle(transit_data, trip_id, now_sec, now_unix, live_gps, live_trip_updates)
        if result is not None:
            vehicles.append(result)
    return jsonify({"vehicles": vehicles})


@app.route("/api/reroute_leg", methods=["POST"])
def api_reroute_leg():
    body = request.get_json(silent=True) or {}
    itinerary = body.get("itinerary")
    leg_index = body.get("leg_index")
    if not isinstance(itinerary, dict) or not isinstance(leg_index, int) or isinstance(leg_index, bool):
        return jsonify({"error": "itinerary and leg_index are required"}), 400

    now = datetime.now()
    active_closures = [c for c in get_construction_closures() if is_closure_active_at(c, now)]
    closure_index = GeoPointIndex(active_closures) if active_closures else None
    active_today = transit_data.active_service_ids(now.date())
    active_yesterday = transit_data.active_service_ids(now.date() - timedelta(days=1))

    updated_itinerary, reason = reroute_bike_leg(
        itinerary, leg_index, closure_index, transit_data, active_today, active_yesterday,
    )
    if updated_itinerary is None:
        return jsonify({"error": reason}), 404

    return jsonify({"itinerary": updated_itinerary})


if __name__ == "__main__":
    app.run(debug=True)
