import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

COMPUTE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
REQUEST_TIMEOUT_SEC = 20
FIELD_MASK = (
    "routes.duration,routes.distanceMeters,"
    "routes.legs.steps.travelMode,routes.legs.steps.staticDuration,"
    "routes.legs.steps.distanceMeters,"
    "routes.legs.steps.transitDetails.transitLine.vehicle.type,"
    "routes.legs.steps.transitDetails.transitLine.nameShort,"
    "routes.legs.steps.transitDetails.transitLine.name,"
    "routes.legs.steps.transitDetails.stopDetails.departureTime,"
    "routes.legs.steps.transitDetails.stopDetails.arrivalTime,"
    "routes.legs.steps.transitDetails.stopDetails.departureStop.name,"
    "routes.legs.steps.transitDetails.stopDetails.arrivalStop.name"
)

# Empirically verified against the live API (2026-08-14), transitPreferences.allowedTravelModes
# is NOT a hard filter (routes using an excluded vehicle type still came back), so mode selection
# is done client-side by scanning each alternative's steps for this vehicle.type instead.
STM_BUS_VEHICLE_TYPE = "BUS"
STM_METRO_VEHICLE_TYPE = "SUBWAY"
REM_VEHICLE_TYPE = "TRAM"


def fetch_transit_alternatives(origin, destination, departure_dt_utc):
    """All TRANSIT route alternatives from Google's Routes API for one origin/destination/time.
    departure_dt_utc must be a timezone-aware UTC datetime already rolled into the future.
    Google rejects past timestamps. Returns a list of route dicts:
    [{"duration_sec": int, "distance_m": int, "legs": [...], "steps": [{"travel_mode":
      "WALK"|"TRANSIT", "duration_sec": int, "distance_m": int, "vehicle_type": str|None,
      "line_name": str|None}]}]

    duration_sec and legs are NOT taken from Google's own top-level routes.duration field, that
    figure can undercount real waiting time (the gap between the requested departure and boarding
    the first vehicle, or between a transfer's arrival and the next vehicle's departure). Instead
    both come from a single pass (_build_legs) that walks the steps in real wall-clock order using
    each transit step's own scheduled stopDetails timestamps, inserting an explicit "wait" leg
    whenever there's a gap, so duration_sec and the visible leg list always agree, and waiting
    time is never silently absorbed into either.

    Raises requests.RequestException / KeyError on failure, callers should handle/log, not
    silently swallow, since a failed live comparison is a meaningful test-harness signal."""
    api_key = os.getenv("GOOGLE_MAPS_ROUTES_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_ROUTES_API_KEY not set in .env")

    body = {
        "origin": {"location": {"latLng": {"latitude": origin["lat"], "longitude": origin["lon"]}}},
        "destination": {"location": {"latLng": {"latitude": destination["lat"], "longitude": destination["lon"]}}},
        "travelMode": "TRANSIT",
        "computeAlternativeRoutes": True,
        "departureTime": departure_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transitPreferences": {"routingPreference": "LESS_WALKING"},
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    response = requests.post(COMPUTE_ROUTES_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()
    data = response.json()

    routes = []
    for route in data.get("routes", []):
        steps = []
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                travel_mode = step.get("travelMode")
                transit_details = step.get("transitDetails", {})
                line = transit_details.get("transitLine", {})
                stop_details = transit_details.get("stopDetails", {})
                steps.append(
                    {
                        "travel_mode": travel_mode,
                        "duration_sec": _parse_duration(step.get("staticDuration")),
                        "distance_m": step.get("distanceMeters", 0),
                        "vehicle_type": line.get("vehicle", {}).get("type"),
                        "line_name": line.get("nameShort") or line.get("name"),
                        "scheduled_arrival": _parse_timestamp(stop_details.get("arrivalTime")),
                        "scheduled_departure": _parse_timestamp(stop_details.get("departureTime")),
                        "departure_stop_name": (stop_details.get("departureStop") or {}).get("name"),
                        "arrival_stop_name": (stop_details.get("arrivalStop") or {}).get("name"),
                    }
                )
        legs, duration_sec = _build_legs(steps, departure_dt_utc, route.get("duration"))
        routes.append(
            {
                "duration_sec": duration_sec,
                "distance_m": route.get("distanceMeters", 0),
                "steps": steps,
                "legs": legs,
            }
        )
    return routes


def _build_legs(steps, departure_dt_utc, fallback_duration):
    """Walks the step sequence in real wall-clock order starting at departure_dt_utc, inserting
    an explicit {"mode": "wait", ...} leg whenever a transit step's scheduled departure is later
    than when the previous leg left off, covers both the initial wait to board and every
    transfer wait, each visible as its own leg rather than folded invisibly into the total.
    Returns (legs, total_duration_sec); legs use raw UTC datetimes for departure/arrival (caller
    formats to local display time). Falls back to ([], Google's own routes.duration) if no step
    carries a scheduled departure, e.g. a walk-only alternative, which TRANSIT mode shouldn't
    normally return, but don't crash if it happens."""
    if not any(s["travel_mode"] == "TRANSIT" and s["scheduled_departure"] is not None for s in steps):
        return [], _parse_duration(fallback_duration)

    legs = []
    current_time = departure_dt_utc
    current_place = "Origin"
    last_idx = len(steps) - 1
    for i, step in enumerate(steps):
        if step["travel_mode"] == "TRANSIT" and step["scheduled_departure"] is not None:
            dep_stop = step["departure_stop_name"] or current_place
            arr_stop = step["arrival_stop_name"] or "?"
            sched_dep = step["scheduled_departure"]
            sched_arr = step["scheduled_arrival"] or (sched_dep + timedelta(seconds=step["duration_sec"]))
            if sched_dep > current_time:
                legs.append({
                    "mode": "wait", "from": current_place, "to": current_place,
                    "departure": current_time, "arrival": sched_dep, "distance_m": 0,
                    "vehicle_type": step["vehicle_type"], "line_name": step["line_name"],
                })
            legs.append({
                "mode": "transit", "from": dep_stop, "to": arr_stop,
                "departure": sched_dep, "arrival": sched_arr, "distance_m": step["distance_m"],
                "vehicle_type": step["vehicle_type"], "line_name": step["line_name"],
            })
            current_time, current_place = sched_arr, arr_stop
        else:
            to_place = "Destination" if i == last_idx else (_next_transit_departure_stop(steps, i) or "Transit stop")
            arrival = current_time + timedelta(seconds=step["duration_sec"])
            legs.append({
                "mode": "walk", "from": current_place, "to": to_place,
                "departure": current_time, "arrival": arrival, "distance_m": step["distance_m"],
                "vehicle_type": None, "line_name": None,
            })
            current_time, current_place = arrival, to_place

    total_sec = max(0, int((current_time - departure_dt_utc).total_seconds()))
    return _merge_walk_legs(legs), total_sec


def _merge_walk_legs(legs):
    """Google's steps are turn-by-turn, so one real walking segment (e.g. origin to the first
    transit stop) often arrives as several consecutive WALK steps with no meaningful intermediate
    stop name, collapse them into one leg per contiguous walk streak, mirroring how this app's
    own engine.router._dijkstra_search merges consecutive walk edges into a single displayed leg."""
    merged = []
    for leg in legs:
        if leg["mode"] == "walk" and merged and merged[-1]["mode"] == "walk":
            prev = merged[-1]
            prev["to"] = leg["to"]
            prev["arrival"] = leg["arrival"]
            prev["distance_m"] += leg["distance_m"]
        else:
            merged.append(dict(leg))
    return merged


def _next_transit_departure_stop(steps, walk_idx):
    for step in steps[walk_idx + 1:]:
        if step["travel_mode"] == "TRANSIT":
            return step["departure_stop_name"]
    return None


def _parse_timestamp(value):
    # Routes API returns RFC3339 UTC "Zulu" timestamps, e.g. "2026-08-14T02:45:00Z"
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _parse_duration(value):
    # Routes API returns durations as a string like "2204s"
    if not value:
        return 0
    return int(str(value).rstrip("s"))
