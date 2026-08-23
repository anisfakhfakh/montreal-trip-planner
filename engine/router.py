import heapq
import itertools
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import numpy as np

from engine.weights_config import (
    BIKE_SPEED_MPS,
    BIKE_STOP_OVERHEAD_FACTOR,
    BIXI_ACCESS_RADIUS_M,
    BIXI_DOCK_TIME_SEC,
    BIXI_PLENTY_THRESHOLD,
    BIXI_RIDE_RADIUS_M,
    BUS_LINE_COLOR,
    CLASSIC_DOWNHILL_FACTOR,
    CLASSIC_UPHILL_FACTOR,
    CONSTRUCTION_PROXIMITY_RADIUS_M,
    CORRESPONDANCE_MAX_DISTANCE_M,
    EBIKE_DOWNHILL_FACTOR,
    EBIKE_SPEED_MPS,
    EBIKE_UPHILL_FACTOR,
    EVENT_PROXIMITY_RADIUS_M,
    MAX_BASE_BIKE_LEG_SEC,
    MAX_DIRECT_WALK_M,
    MAX_HYBRID_BIKE_LEG_SEC,
    MAX_PATTERNS_PER_STOP,
    METRO_BLUE_LINE_DISPLAY_COLOR,
    METRO_BLUE_LINE_REAL_COLOR,
    METRO_STATION_ENTRY_TIME_SEC,
    METRO_STATION_EXIT_TIME_SEC,
    MIN_DISPLAYED_WALK_LEG_SEC,
    ORIGIN_DEST_ACCESS_RADIUS_M,
    PATTERN_LOOKAHEAD_SEC,
    REM_LINE_COLOR,
    ROUTE_TYPE_BUS,
    ROUTE_TYPE_METRO,
    ROUTE_TYPE_REM,
    TRANSFER_PENALTY_SEC,
    TRANSFER_WALK_RADIUS_M,
    WAIT_LEG_MIN_SEC,
    WAIT_RISK_DANGER_SEC,
    WAIT_RISK_WARN_SEC,
    WALK_LEG_HARD_CAP_SEC,
    WALK_SPEED_MPS,
    WALK_STOP_OVERHEAD_FACTOR,
    WALK_TIEBREAK_WEIGHT,
)
from engine.risk import compute_risk_score, next_same_route_wait_sec
from services.osrm_client import osrm_route, osrm_route_alternatives

EARTH_RADIUS_M = 6371000
DYNAMIC_EDGE_WORKERS = 16

ORIGIN = ("origin",)
DEST = ("dest",)
RAIL_ROUTE_TYPES = (ROUTE_TYPE_METRO, ROUTE_TYPE_REM)
ALL_ROUTE_TYPES = frozenset({ROUTE_TYPE_BUS, ROUTE_TYPE_METRO, ROUTE_TYPE_REM})

# Approximate BIXI brand red pending an exact hex from their brand guide (Phase 7 polish item).
BIXI_COLOR = "D6001C"
WALK_COLOR = "555555"

# GTFS bus trip_headsign values are literally French direction words. Translate them to a
# single English compass letter, matching the abbreviation already used for street addresses in
# static/js/map.js's STREET_DIRECTION_TRANSLATIONS, rather than a spelled-out word. Metro/REM
# headsigns are real place names/branch codes and must NOT go through this table.
DIRECTION_TRANSLATIONS = {"Nord": "N", "Sud": "S", "Est": "E", "Ouest": "W"}

# Bus/metro headsigns sometimes carry a trailing STM-internal note after a " -" separator, e.g.
# "Est - Vers le centre-ville de Montreal trajet 1 gare d'autocars de Montreal" or
# "Station Montmorency -Zone B". Not useful to riders, so it's stripped before display. REM
# headsigns deliberately keep their own " - " (e.g. "A3 - Anse-a-l'Orme", see
# _dijkstra_search's headsign handling), so this must only run for bus/metro.
_HEADSIGN_EXTENSION_RE = re.compile(r"\s-")


def _strip_headsign_extension(headsign):
    if headsign is None:
        return headsign
    match = _HEADSIGN_EXTENSION_RE.search(headsign)
    return headsign[:match.start()].strip() if match else headsign


def _translate_direction(headsign):
    if headsign is None:
        return headsign
    return DIRECTION_TRANSLATIONS.get(headsign, headsign)


def _transit_label(route_type, route_short_name, route_color):
    """Human-readable "mode of transportation" label for a transit/wait leg, e.g. "Bus 105",
    "Metro line 2", "REM". Metro's route_short_name is already the real STM line number
    ("1"/"2"/"4"/"5"), so no color->name lookup is needed."""
    if route_type == ROUTE_TYPE_BUS:
        return f"Bus {route_short_name}"
    if route_type == ROUTE_TYPE_METRO:
        return f"Metro line {route_short_name}"
    if route_type == ROUTE_TYPE_REM:
        return "REM"
    return route_short_name or "transit"


def _wait_risk(gap_sec, transit_label, next_wait_sec):
    """Plain-language risk sign for the buffer before a scheduled departure. Replaces the old
    numeric "reliability" score, which users found too opaque/inaccurate to act on. When a risk
    level fires, also names how long you'd be stuck if you missed this one (real GTFS
    next-same-route-departure lookup, not a guess)."""
    if gap_sec <= WAIT_RISK_DANGER_SEC:
        level, note = "danger", f"high risk of missing {transit_label}"
    elif gap_sec <= WAIT_RISK_WARN_SEC:
        level, note = "warn", f"moderate risk of missing {transit_label}"
    else:
        return None, None
    if next_wait_sec is not None:
        note += f"; next {transit_label} scheduled {round(next_wait_sec / 60)} min later"
    return level, note


def _bike_risk(leg, bixi_stations):
    """Plain-language risk sign for real-time bike availability at a BIXI leg's departure
    station, checking whichever bike type (classic/electric) this leg actually uses."""
    station = bixi_stations.get(leg.get("from_stop_id"))
    if station is None:
        return None, None
    ebikes = station.get("ebikes_available", 0)
    is_electric = leg.get("bike_type") == "electric"
    count = ebikes if is_electric else max(station.get("bikes_available", 0) - ebikes, 0)
    kind = "electric" if is_electric else "classic"
    if count == 0:
        return "danger", f"no {kind} Bixis available"
    if count < BIXI_PLENTY_THRESHOLD:
        return "warn", f"few {kind} Bixis available"
    return None, None


def _annotate_bike_risk(legs, bixi_stations):
    for leg in legs:
        if leg["mode"] == "bike":
            leg["risk_level"], leg["risk_note"] = _bike_risk(leg, bixi_stations)
    return legs


def _walk_duration_sec(distance_m):
    return distance_m / WALK_SPEED_MPS * WALK_STOP_OVERHEAD_FACTOR


def _bike_duration_sec(distance_m, ascend_m, descend_m, speed_mps, uphill_factor, downhill_factor):
    flat_m = max(distance_m - ascend_m - descend_m, 0)
    duration = (
        flat_m / speed_mps
        + ascend_m / (speed_mps * uphill_factor)
        + descend_m / (speed_mps * downhill_factor)
    )
    return duration * BIKE_STOP_OVERHEAD_FACTOR + BIXI_DOCK_TIME_SEC


def haversine_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class BixiIndex:
    def __init__(self, bixi_stations):
        self.stations = bixi_stations
        self.ids = np.array(list(bixi_stations.keys()))
        self.lats = np.array([bixi_stations[s]["lat"] for s in self.ids])
        self.lons = np.array([bixi_stations[s]["lon"] for s in self.ids])

    def nearby(self, lat, lon, radius_m):
        if len(self.ids) == 0:
            return []
        lat1, lat2 = np.radians(lat), np.radians(self.lats)
        dlat = lat2 - lat1
        dlon = np.radians(self.lons - lon)
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        distances = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
        mask = distances <= radius_m
        return list(zip(self.ids[mask], distances[mask]))


class GeoPointIndex:
    """Same numpy-vectorized nearby-point lookup as BixiIndex, but backed by a plain list
    instead of an id-keyed dict since construction closures and events have no natural unique
    key the rest of the app cares about. Shared by both datasets since the lookup is identical."""

    def __init__(self, points):
        self.points = points
        self.lats = np.array([p["lat"] for p in points])
        self.lons = np.array([p["lon"] for p in points])

    def nearby(self, lat, lon, radius_m):
        if len(self.points) == 0:
            return []
        lat1, lat2 = np.radians(lat), np.radians(self.lats)
        dlat = lat2 - lat1
        dlon = np.radians(self.lons - lon)
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        distances = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
        mask = distances <= radius_m
        return [self.points[i] for i in np.nonzero(mask)[0]]


_CONSTRUCTION_PATH_SAMPLE_CAP = 30


def _sample_path_hits(path, geo_index, radius_m, sample_cap=_CONSTRUCTION_PATH_SAMPLE_CAP):
    """Every distinct point (closure or event) within radius_m of a bounded sample of points
    along a leg's path, not every raw OSRM polyline point, since this is a proximity
    approximation, not exact geometry intersection, and dense polylines shouldn't cost more to
    check than sparse ones. Deduped by id (a dict, not a list) since the same point can be
    nearest to more than one sampled path point."""
    if geo_index is None:
        return {}
    stride = max(1, len(path) // sample_cap)
    hits = {}
    for lat, lon in path[::stride]:
        for hit in geo_index.nearby(lat, lon, radius_m):
            hits[hit["id"]] = hit
    return hits


def _annotate_construction_risk(legs, closure_index):
    """Flags any bike leg whose path passes near an active construction closure. Stores every
    distinct closure hit (construction_hits, used for counting/map markers) plus a display
    string built from the first one (construction_note, unchanged wording). Walk/transit legs
    aren't flagged since construction closures affect where a cyclist can ride, not a pedestrian
    or a bus/metro/REM route, so the warning would just be noise there."""
    for leg in legs:
        if leg["mode"] != "bike":
            continue
        hits = _sample_path_hits(leg["path"], closure_index, CONSTRUCTION_PROXIMITY_RADIUS_M)
        if hits:
            leg["construction_hits"] = list(hits.values())
            first = leg["construction_hits"][0]
            leg["construction_note"] = f"Passes through active construction ({first['occupancy'] or first['reason']})"
    return legs


def _annotate_event_risk(legs, event_index):
    """Same idea as _annotate_construction_risk, but bike legs only. Events don't feed the
    reroute button or get a display note on other leg types, only the BIXI-scoped
    construction_events_count metric."""
    for leg in legs:
        if leg["mode"] != "bike":
            continue
        hits = _sample_path_hits(leg["path"], event_index, EVENT_PROXIMITY_RADIUS_M)
        if hits:
            leg["event_hits"] = list(hits.values())
    return legs


def construction_events_count(legs):
    """Count of distinct construction closures + events crossed by the BIXI portion of an
    itinerary, deduped across all bike legs. None (not 0) if the itinerary has no bike leg at
    all since the frontend shows that as "-", not "0"."""
    bike_legs = [leg for leg in legs if leg["mode"] == "bike"]
    if not bike_legs:
        return None
    seen = set()
    for leg in bike_legs:
        for hit in leg.get("construction_hits", []):
            seen.add(("construction", hit["id"]))
        for hit in leg.get("event_hits", []):
            seen.add(("event", hit["id"]))
    return len(seen)


def _next_departures_by_pattern(
    transit_data, stop_id, after_sec, active_today, active_yesterday,
    only_route_types=None, exclude_route_types=(),
    max_lookahead_sec=PATTERN_LOOKAHEAD_SEC, max_patterns=MAX_PATTERNS_PER_STOP,
):
    """Earliest reachable departure per distinct (route, next stop) pattern from this stop,
    not just the single soonest departure overall. A stop is often shared by several
    routes/directions (e.g. both directions of a line boarding from the same stop_id), so
    taking only the earliest departure would silently hide a different, useful direction/route
    that happens to leave a bit later, and Dijkstra would never get the chance to compare them."""
    entries = transit_data.stop_departures.get(stop_id)
    if not entries:
        return []
    deps = [e[0] for e in entries]
    idx = _bisect_left(deps, after_sec)
    end_sec = after_sec + max_lookahead_sec
    seen = {}
    for i in range(idx, len(entries)):
        dep_sec, trip_id, idx_in_trip, service_id, day_offset = entries[i]
        if dep_sec > end_sec:
            break
        active_set = active_yesterday if day_offset == 1 else active_today
        if service_id not in active_set:
            continue
        trip_stops = transit_data.trip_stops[trip_id]
        if idx_in_trip + 1 >= len(trip_stops):
            continue
        route_id = transit_data.trip_route[trip_id]
        route_type = transit_data.routes[route_id][4]
        if only_route_types is not None and route_type not in only_route_types:
            continue
        if route_type in exclude_route_types:
            continue
        pattern = (route_id, trip_stops[idx_in_trip + 1][0])
        if pattern not in seen:
            seen[pattern] = (dep_sec, trip_id, idx_in_trip)
            if len(seen) >= max_patterns:
                break
    return list(seen.values())


def _bisect_left(sorted_list, value):
    lo, hi = 0, len(sorted_list)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_list[mid] < value:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _resolve_edge(walk_graph, from_node, to_node, from_lat, from_lon, to_lat, to_lon, mode):
    """Real distance+geometry for a static graph edge: cache hit, else a live local OSRM
    call, else haversine as a last-resort safety net (e.g. Docker not running)."""
    edge = walk_graph.lookup(from_node, to_node, mode)
    if edge is not None:
        return edge
    edge = osrm_route(from_lat, from_lon, to_lat, to_lon, mode)
    if edge is not None:
        return edge
    return {
        "distance_m": haversine_m(from_lat, from_lon, to_lat, to_lon),
        "geometry": [[from_lat, from_lon], [to_lat, to_lon]],
    }


def _static_neighbors(walk_graph, transit_data, bixi_index, node, mode, target_type, lat, lon, radius_m):
    """Who's reachable by `mode` from a *static* graph node (a stop or BIXI dock, never the
    dynamic origin/destination point, which can't be precomputed). Prefers the precomputed
    neighbor list saved alongside the edge cache; falls back to the original live haversine
    radius scan if this cache predates that precompute (or lacks this specific node/mode,
    e.g. a BIXI station added after the cache was last built)."""
    precomputed = walk_graph.neighbors(node, mode)
    if precomputed is not None:
        return [n for n in precomputed if n[0] == target_type]
    if target_type == "stop":
        return [("stop", stop_id) for stop_id, _ in transit_data.nearby_stops(lat, lon, radius_m)]
    return [("bixi", station_id) for station_id, _ in bixi_index.nearby(lat, lon, radius_m)]


def _resolve_dynamic_edge(fixed_lat, fixed_lon, other_lat, other_lon, mode, fixed_first):
    """Real distance+geometry for an edge touching a dynamic endpoint (origin/destination
    click point), which is never in the precomputed cache. Live OSRM call, haversine
    fallback if the OSRM containers aren't reachable."""
    if fixed_first:
        edge = osrm_route(fixed_lat, fixed_lon, other_lat, other_lon, mode)
    else:
        edge = osrm_route(other_lat, other_lon, fixed_lat, fixed_lon, mode)
    if edge is not None:
        return edge
    d = haversine_m(fixed_lat, fixed_lon, other_lat, other_lon)
    geometry = [[fixed_lat, fixed_lon], [other_lat, other_lon]] if fixed_first else [[other_lat, other_lon], [fixed_lat, fixed_lon]]
    return {"distance_m": d, "geometry": geometry}


def _bike_speed_params(bike_type):
    if bike_type == "electric":
        return EBIKE_SPEED_MPS, EBIKE_UPHILL_FACTOR, EBIKE_DOWNHILL_FACTOR
    return BIKE_SPEED_MPS, CLASSIC_UPHILL_FACTOR, CLASSIC_DOWNHILL_FACTOR


def find_bike_detour(leg, closure_index):
    """Given a BIXI leg, checks whether it currently passes near active construction and, if
    so, tries to find a real alternate OSRM route between the same two stations that clears
    every currently-flagged closure along the original path. Returns (new_leg, delta_sec) on
    success, or None if there's nothing to avoid or no clearing alternative exists. Station
    choice, from_name/to_name, dep_sec, and bike_type are all left untouched, only the
    path/ascend/descend/arr_sec of this one leg change."""
    obstacles = _sample_path_hits(leg["path"], closure_index, CONSTRUCTION_PROXIMITY_RADIUS_M)
    if not obstacles:
        return None

    from_lat, from_lon = leg["from"]
    to_lat, to_lon = leg["to"]
    alternatives = osrm_route_alternatives(from_lat, from_lon, to_lat, to_lon, "bike")

    def clears_all_obstacles(geometry):
        stride = max(1, len(geometry) // _CONSTRUCTION_PATH_SAMPLE_CAP)
        for lat, lon in geometry[::stride]:
            for obstacle in obstacles.values():
                if haversine_m(lat, lon, obstacle["lat"], obstacle["lon"]) <= CONSTRUCTION_PROXIMITY_RADIUS_M:
                    return False
        return True

    clearing = [alt for alt in alternatives if clears_all_obstacles(alt["geometry"])]
    if not clearing:
        return None
    best = min(clearing, key=lambda alt: alt["distance_m"])

    speed_mps, uphill_factor, downhill_factor = _bike_speed_params(leg.get("bike_type"))
    new_duration = _bike_duration_sec(best["distance_m"], 0.0, 0.0, speed_mps, uphill_factor, downhill_factor)
    old_duration = leg["arr_sec"] - leg["dep_sec"]

    new_leg = dict(leg)
    new_leg["path"] = best["geometry"]
    new_leg["ascend_m"] = 0.0
    new_leg["descend_m"] = 0.0
    new_leg["arr_sec"] = leg["dep_sec"] + new_duration
    new_leg.pop("construction_note", None)
    new_leg.pop("construction_hits", None)
    return new_leg, new_duration - old_duration


def _nearby_candidates(transit_data, bixi_index, bixi_stations, lat, lon):
    """Stops + BIXI stations within walking distance of a fixed point (haversine radius
    filter only, to decide which candidates deserve a real routing call, not the reported
    distance itself)."""
    candidates = []
    for stop_id, _ in transit_data.nearby_stops(lat, lon, ORIGIN_DEST_ACCESS_RADIUS_M):
        name, s_lat, s_lon = transit_data.stops[stop_id]
        candidates.append((("stop", stop_id), name, s_lat, s_lon))
    for station_id, _ in bixi_index.nearby(lat, lon, ORIGIN_DEST_ACCESS_RADIUS_M):
        s = bixi_stations[station_id]
        candidates.append((("bixi", station_id), s["name"], s["lat"], s["lon"]))
    return candidates


def _resolve_dynamic_edges_batch(candidates, fixed_lat, fixed_lon, fixed_first):
    """Resolves real walking distance+geometry between one fixed point (origin or
    destination) and a small, radius-bounded set of candidates, in parallel local OSRM
    calls. Returns {node_key: {"name", "lat", "lon", "distance_m", "geometry"}}."""
    def _one(candidate):
        node_key, name, lat, lon = candidate
        edge = _resolve_dynamic_edge(fixed_lat, fixed_lon, lat, lon, "foot", fixed_first)
        return node_key, {**edge, "name": name, "lat": lat, "lon": lon}

    edges = {}
    with ThreadPoolExecutor(max_workers=DYNAMIC_EDGE_WORKERS) as executor:
        for node_key, edge in executor.map(_one, candidates):
            edges[node_key] = edge
    return edges


def _resolve_dynamic_context(transit_data, bixi_index, bixi_stations, origin, destination, departure_dt):
    """Everything about an origin/destination pair that is independent of which modes a
    search allows: real-time-of-day bookkeeping and the radius-bounded live-OSRM edges from
    the dynamic origin/destination points. Resolved once and reused across the best/transit-
    only/BIXI-only searches so they don't redo the same local-OSRM network calls three times."""
    active_today = transit_data.active_service_ids(departure_dt.date())
    active_yesterday = transit_data.active_service_ids(departure_dt.date() - timedelta(days=1))
    query_time_sec = departure_dt.hour * 3600 + departure_dt.minute * 60 + departure_dt.second

    origin_candidates = _nearby_candidates(transit_data, bixi_index, bixi_stations, origin["lat"], origin["lon"])
    origin_edges = _resolve_dynamic_edges_batch(origin_candidates, origin["lat"], origin["lon"], fixed_first=True)

    dest_candidates = _nearby_candidates(transit_data, bixi_index, bixi_stations, destination["lat"], destination["lon"])
    dest_edges = _resolve_dynamic_edges_batch(dest_candidates, destination["lat"], destination["lon"], fixed_first=False)

    direct_edge = None
    direct_walk_m = haversine_m(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
    if direct_walk_m <= MAX_DIRECT_WALK_M:
        direct_edge = _resolve_dynamic_edge(
            origin["lat"], origin["lon"], destination["lat"], destination["lon"], "foot", fixed_first=True
        )

    return {
        "active_today": active_today, "active_yesterday": active_yesterday, "query_time_sec": query_time_sec,
        "origin_edges": origin_edges, "dest_edges": dest_edges, "direct_edge": direct_edge,
    }


def _dijkstra_search(transit_data, bixi_stations, bixi_index, walk_graph, origin, destination, ctx, max_settled=20000, allow_ebike=False, allowed_route_types=ALL_ROUTE_TYPES, allow_bixi=True, max_walk_leg_sec=None, max_bike_leg_sec=None, closure_index=None, event_index=None):
    """Single time-dependent Dijkstra search, optionally restricted to a subset of modes
    (used to compute the mode-limited alternatives alongside the unrestricted best route).
    Mode restriction is a hard graph constraint: edges into the disallowed mode's nodes, and
    walk edges longer than max_walk_leg_sec, are simply never offered. Not a soft cost bias,
    so results stay exact.

    Stop nodes are keyed ("stop", stop_id, riding_trip_id), where riding_trip_id is None if this
    arrival walked/biked in, or the specific trip_id if still aboard a vehicle. Without this,
    a stop reached by a merely-slightly-cheaper walk can permanently block a fresh-boarding
    or ride-continuation arrival at the exact same (stop_id, None) node, even when that
    arrival is a strictly better *state* to be in (already boarded, no further wait needed).
    Dijkstra's cost comparison alone can't see that a walk-arrival still owes a future
    boarding wait that a ride-arrival doesn't. Keeping them as separate node identities lets
    both be explored on their own merits instead of one shadowing the other."""
    active_today = ctx["active_today"]
    active_yesterday = ctx["active_yesterday"]
    query_time_sec = ctx["query_time_sec"]
    origin_edges = ctx["origin_edges"]
    dest_edges = ctx["dest_edges"]
    bus_types = allowed_route_types - set(RAIL_ROUTE_TYPES)
    rail_types = allowed_route_types & set(RAIL_ROUTE_TYPES)

    def walk_ok(walk_dur):
        return max_walk_leg_sec is None or walk_dur <= max_walk_leg_sec

    def bike_ok(total_bike_dur):
        return max_bike_leg_sec is None or total_bike_dur <= max_bike_leg_sec

    # `dist` holds each node's real, physically-accurate arrival time, used for schedule
    # lookups, leg construction, and the final displayed result. `cost` is a separate value
    # Dijkstra actually optimizes: real time plus TRANSFER_PENALTY_SEC per transit boarding
    # after the first, so a route that boards an extra vehicle only has to win on cost, not
    # on raw arrival time, see TRANSFER_PENALTY_SEC's comment in weights_config.py.
    dist = {ORIGIN: query_time_sec}
    cost = {ORIGIN: query_time_sec}
    prev = {}
    # Cumulative duration of the continuous walk-only streak ending at each node (0 if the
    # node was reached by transit/bike, which breaks the streak), needed because
    # _merge_legs later concatenates consecutive walk edges into one displayed leg, so the
    # cap has to apply to that whole chain, not just the single graph edge being considered.
    walk_streak = {}
    # Same idea as walk_streak, but for continuous BIXI riding (resets on any walk or transit
    # edge), lets the "shorter BIXI legs" alternative cap the whole merged bike leg, not just
    # a single dock-to-dock graph edge.
    bike_streak = {}
    # Number of transit boardings on the best-cost path to each node so far (0 = none yet).
    boardings = {}
    counter = itertools.count()
    heap = [(query_time_sec, next(counter), ORIGIN)]
    settled = set()

    if ctx["direct_edge"] is not None:
        direct_walk_dur = _walk_duration_sec(ctx["direct_edge"]["distance_m"])
        if walk_ok(direct_walk_dur):
            arrival = query_time_sec + direct_walk_dur
            dist[DEST] = arrival
            cost[DEST] = arrival
            prev[DEST] = (ORIGIN, {
                "mode": "walk", "from": [origin["lat"], origin["lon"]], "to": [destination["lat"], destination["lon"]],
                "from_name": "Origin", "to_name": "Destination", "dep_sec": query_time_sec, "arr_sec": arrival,
                "path": ctx["direct_edge"]["geometry"],
            })
            heapq.heappush(heap, (arrival, next(counter), DEST))

    settled_count = 0
    while heap and settled_count < max_settled:
        cost_value, _, node = heapq.heappop(heap)
        if node in settled:
            continue
        if cost_value > cost.get(node, math.inf):
            continue
        settled.add(node)
        settled_count += 1
        arrival_sec = dist[node]

        if node == DEST:
            break

        def relax(neighbor, new_arrival, leg, streak=0, bike_streak_val=0, is_boarding=False):
            penalty = TRANSFER_PENALTY_SEC if is_boarding and boardings.get(node, 0) > 0 else 0
            edge_duration = new_arrival - arrival_sec
            if leg.get("mode") == "walk":
                edge_duration *= WALK_TIEBREAK_WEIGHT
            new_cost = cost[node] + edge_duration + penalty
            if new_cost < cost.get(neighbor, math.inf):
                cost[neighbor] = new_cost
                dist[neighbor] = new_arrival
                prev[neighbor] = (node, leg)
                walk_streak[neighbor] = streak
                bike_streak[neighbor] = bike_streak_val
                boardings[neighbor] = boardings.get(node, 0) + (1 if is_boarding else 0)
                heapq.heappush(heap, (new_cost, next(counter), neighbor))

        if node == ORIGIN:
            for node_key, edge in origin_edges.items():
                if node_key[0] == "bixi" and not allow_bixi:
                    continue
                walk_dur = _walk_duration_sec(edge["distance_m"])
                if not walk_ok(walk_dur):
                    continue
                search_node_key = (node_key[0], node_key[1], None) if node_key[0] in ("stop", "bixi") else node_key
                relax(search_node_key, arrival_sec + walk_dur, {
                    "mode": "walk", "from": [origin["lat"], origin["lon"]], "to": [edge["lat"], edge["lon"]],
                    "from_name": "Origin", "to_name": edge["name"], "dep_sec": arrival_sec, "arr_sec": arrival_sec + walk_dur,
                    "path": edge["geometry"],
                }, streak=walk_dur)

        elif node[0] == "stop":
            stop_id = node[1]
            name, lat, lon = transit_data.stops[stop_id]

            # How we arrived here: still riding a trip (continuing), or just walked/biked in
            # (a fresh boarding). The node's own identity says which (see docstring), not
            # a comparison against whatever else might have reached this stop. The station
            # entry/exit overhead must only ever be charged once per real ride, at true
            # boarding and true alighting, never at the intermediate stops of a trip we're
            # already aboard.
            riding = node[2] is not None
            arrived_leg = prev[node][1] if node in prev else None
            exit_overhead = 0
            if riding and arrived_leg["route_type"] in (ROUTE_TYPE_METRO, ROUTE_TYPE_REM):
                exit_overhead = METRO_STATION_EXIT_TIME_SEC

            if riding:
                trip_id = arrived_leg["trip_id"]
                to_idx = arrived_leg["to_idx"]
                fold = arrived_leg["fold"]
                trip_stops = transit_data.trip_stops[trip_id]
                if to_idx + 1 < len(trip_stops):
                    next_stop_id, next_arr_sec, _ = trip_stops[to_idx + 1]
                    next_name, next_lat, next_lon = transit_data.stops[next_stop_id]
                    arrival = next_arr_sec - fold
                    relax(("stop", next_stop_id, trip_id), arrival, {
                        "mode": "transit", "trip_id": trip_id, "route_id": arrived_leg["route_id"],
                        "route_short_name": arrived_leg["route_short_name"], "route_color": arrived_leg["route_color"],
                        "route_text_color": arrived_leg["route_text_color"], "route_type": arrived_leg["route_type"],
                        "transit_label": arrived_leg["transit_label"], "trip_headsign": arrived_leg["trip_headsign"],
                        "from_stop": stop_id, "to_stop": next_stop_id,
                        "from": [lat, lon], "to": [next_lat, next_lon],
                        "from_name": name, "to_name": next_name,
                        "dep_sec": arrival_sec, "arr_sec": arrival,
                        "to_idx": to_idx + 1, "fold": fold, "num_stops": 1,
                    })

            if bus_types or rail_types:
                # Fresh boarding: the first-ever boarding of a ride, or a transfer to a different
                # trip/route. Pays the exit overhead for the ride just left (0 unless it was
                # metro/REM) plus the entry overhead for the one about to be boarded. Every
                # distinct (route, next stop) pattern gets its own candidate edge, not just the
                # single soonest departure, so a direction/route that departs a bit later never
                # gets silently hidden by a busier one leaving sooner.
                search_from = arrival_sec + exit_overhead
                candidates = []
                if bus_types:
                    candidates += _next_departures_by_pattern(
                        transit_data, stop_id, search_from, active_today, active_yesterday,
                        only_route_types=bus_types,
                    )
                if rail_types:
                    candidates += _next_departures_by_pattern(
                        transit_data, stop_id, search_from + METRO_STATION_ENTRY_TIME_SEC, active_today, active_yesterday,
                        only_route_types=rail_types,
                    )

                for dep_sec, trip_id, idx_in_trip in candidates:
                    trip_stops = transit_data.trip_stops[trip_id]
                    next_stop_id, next_arr_sec, _ = trip_stops[idx_in_trip + 1]
                    # if this departure was a folded (yesterday-service) entry, fold the arrival the same way
                    orig_dep_sec = trip_stops[idx_in_trip][2]
                    fold = orig_dep_sec - dep_sec if orig_dep_sec != dep_sec else 0
                    route_id = transit_data.trip_route[trip_id]
                    route_short_name, _, route_color, route_text_color, route_type = transit_data.routes[route_id]
                    next_name, next_lat, next_lon = transit_data.stops[next_stop_id]
                    if route_type == ROUTE_TYPE_BUS:
                        display_color = BUS_LINE_COLOR
                    elif route_type == ROUTE_TYPE_REM:
                        display_color = REM_LINE_COLOR
                    elif route_type == ROUTE_TYPE_METRO and route_color == METRO_BLUE_LINE_REAL_COLOR:
                        display_color = METRO_BLUE_LINE_DISPLAY_COLOR
                    else:
                        display_color = route_color or "000000"
                    headsign = transit_data.trip_headsign.get(trip_id)
                    if route_type == ROUTE_TYPE_BUS:
                        headsign = _translate_direction(_strip_headsign_extension(headsign))
                    elif route_type == ROUTE_TYPE_METRO:
                        headsign = _strip_headsign_extension(headsign)
                    arrival = next_arr_sec - fold
                    relax(("stop", next_stop_id, trip_id), arrival, {
                        "mode": "transit", "trip_id": trip_id, "route_id": route_id,
                        "route_short_name": route_short_name, "route_color": display_color,
                        "route_text_color": route_text_color or "FFFFFF", "route_type": route_type,
                        "transit_label": _transit_label(route_type, route_short_name, display_color),
                        "trip_headsign": headsign,
                        "from_stop": stop_id, "to_stop": next_stop_id,
                        "from": [lat, lon], "to": [next_lat, next_lon],
                        "from_name": name, "to_name": next_name,
                        "dep_sec": dep_sec, "arr_sec": arrival,
                        "to_idx": idx_in_trip + 1, "fold": fold, "num_stops": 1,
                    }, is_boarding=True)

            for _, other_stop_id in _static_neighbors(walk_graph, transit_data, bixi_index, ("stop", stop_id), "foot", "stop", lat, lon, TRANSFER_WALK_RADIUS_M):
                if other_stop_id == stop_id:
                    continue
                other_stop = transit_data.stops.get(other_stop_id)
                if other_stop is None:
                    continue
                other_name, other_lat, other_lon = other_stop
                edge = _resolve_edge(walk_graph, ("stop", stop_id), ("stop", other_stop_id), lat, lon, other_lat, other_lon, "foot")
                raw_walk_dur = _walk_duration_sec(edge["distance_m"])
                # Cap check must include exit_overhead since it's part of this edge's actual
                # dep_sec/arr_sec span (walk_dur below), so checking the cap against raw_walk_dur
                # alone let a metro/REM-egress walk through even when raw+overhead exceeded the cap.
                walk_dur = raw_walk_dur + exit_overhead
                total_walk = walk_streak.get(node, 0) + walk_dur
                if not walk_ok(total_walk):
                    continue
                relax(("stop", other_stop_id, None), arrival_sec + walk_dur, {
                    "mode": "walk", "from": [lat, lon], "to": [other_lat, other_lon],
                    "from_name": name, "to_name": other_name, "dep_sec": arrival_sec, "arr_sec": arrival_sec + walk_dur,
                    "path": edge["geometry"],
                }, streak=total_walk)

            if allow_bixi:
                for _, station_id in _static_neighbors(walk_graph, transit_data, bixi_index, ("stop", stop_id), "foot", "bixi", lat, lon, BIXI_ACCESS_RADIUS_M):
                    s = bixi_stations.get(station_id)
                    if s is None:
                        continue
                    edge = _resolve_edge(walk_graph, ("stop", stop_id), ("bixi", station_id), lat, lon, s["lat"], s["lon"], "foot")
                    raw_walk_dur = _walk_duration_sec(edge["distance_m"])
                    walk_dur = raw_walk_dur + exit_overhead
                    total_walk = walk_streak.get(node, 0) + walk_dur
                    if not walk_ok(total_walk):
                        continue
                    relax(("bixi", station_id, None), arrival_sec + walk_dur, {
                        "mode": "walk", "from": [lat, lon], "to": [s["lat"], s["lon"]],
                        "from_name": name, "to_name": s["name"], "dep_sec": arrival_sec, "arr_sec": arrival_sec + walk_dur,
                        "path": edge["geometry"],
                    }, streak=total_walk)

            dest_edge = dest_edges.get(("stop", stop_id))
            if dest_edge is not None:
                raw_walk_dur = _walk_duration_sec(dest_edge["distance_m"])
                walk_dur = raw_walk_dur + exit_overhead
                total_walk = walk_streak.get(node, 0) + walk_dur
                if walk_ok(total_walk):
                    relax(DEST, arrival_sec + walk_dur, {
                        "mode": "walk", "from": [lat, lon], "to": [destination["lat"], destination["lon"]],
                        "from_name": name, "to_name": "Destination", "dep_sec": arrival_sec, "arr_sec": arrival_sec + walk_dur,
                        "path": dest_edge["geometry"],
                    }, streak=total_walk)

        elif node[0] == "bixi":
            station_id = node[1]
            # node[2] is the bike type we're currently riding, or None if we haven't checked
            # one out yet. Once we're on a classic or electric bike we stay on it through
            # dock-to-dock hops; switching only happens by actually docking and walking away.
            # That keeps _merge_legs's bike_type check (see its docstring) happy for a real
            # continuous ride instead of fragmenting it every time an intermediate station's
            # inventory differs.
            current_type = node[2]
            bare_node = ("bixi", station_id)
            s = bixi_stations[station_id]
            if current_type is None:
                # Not riding yet, so this station's live inventory decides what we can check out.
                ebikes_here = s.get("ebikes_available", 0)
                classic_bikes = max(s["bikes_available"] - ebikes_here, 0)
                offer_classic = classic_bikes > 0
                offer_electric = allow_ebike and ebikes_here > 0
            else:
                # Already riding, so this station is just a waypoint we're passing through, not
                # somewhere we're re-renting. The bike in hand counts as available regardless of
                # what this dock's inventory says; only the original checkout station gates it.
                offer_classic = current_type == "classic"
                offer_electric = allow_ebike and current_type == "electric"

            if offer_classic or offer_electric:
                for _, other_id in _static_neighbors(walk_graph, transit_data, bixi_index, bare_node, "bike", "bixi", s["lat"], s["lon"], BIXI_RIDE_RADIUS_M):
                    if other_id == station_id:
                        continue
                    other = bixi_stations.get(other_id)
                    if other is None:
                        continue
                    edge = _resolve_edge(walk_graph, bare_node, ("bixi", other_id), s["lat"], s["lon"], other["lat"], other["lon"], "bike")
                    ascend_m = edge.get("ascend_m", 0.0)
                    descend_m = edge.get("descend_m", 0.0)

                    if offer_classic:
                        bike_dur = _bike_duration_sec(
                            edge["distance_m"], ascend_m, descend_m,
                            BIKE_SPEED_MPS, CLASSIC_UPHILL_FACTOR, CLASSIC_DOWNHILL_FACTOR,
                        )
                        total_bike = bike_streak.get(node, 0) + bike_dur
                        if bike_ok(total_bike):
                            relax(("bixi", other_id, "classic"), arrival_sec + bike_dur, {
                                "mode": "bike", "bike_type": "classic", "from_stop_id": station_id,
                                "from": [s["lat"], s["lon"]], "to": [other["lat"], other["lon"]],
                                "from_name": s["name"], "to_name": other["name"], "dep_sec": arrival_sec, "arr_sec": arrival_sec + bike_dur,
                                "path": edge["geometry"], "ascend_m": ascend_m, "descend_m": descend_m,
                            }, bike_streak_val=total_bike)

                    if offer_electric:
                        bike_dur = _bike_duration_sec(
                            edge["distance_m"], ascend_m, descend_m,
                            EBIKE_SPEED_MPS, EBIKE_UPHILL_FACTOR, EBIKE_DOWNHILL_FACTOR,
                        )
                        total_bike = bike_streak.get(node, 0) + bike_dur
                        if bike_ok(total_bike):
                            relax(("bixi", other_id, "electric"), arrival_sec + bike_dur, {
                                "mode": "bike", "bike_type": "electric", "from_stop_id": station_id,
                                "from": [s["lat"], s["lon"]], "to": [other["lat"], other["lon"]],
                                "from_name": s["name"], "to_name": other["name"], "dep_sec": arrival_sec, "arr_sec": arrival_sec + bike_dur,
                                "path": edge["geometry"], "ascend_m": ascend_m, "descend_m": descend_m,
                            }, bike_streak_val=total_bike)

            # Walking away means docking the bike first if we're riding one, and that needs a
            # free dock at this station right now. A rider who just walked in has nothing to
            # dock, so that case is always free.
            can_end_ride_here = current_type is None or s["docks_available"] > 0

            if can_end_ride_here:
                for _, stop_id in _static_neighbors(walk_graph, transit_data, bixi_index, bare_node, "foot", "stop", s["lat"], s["lon"], TRANSFER_WALK_RADIUS_M):
                    stop = transit_data.stops.get(stop_id)
                    if stop is None:
                        continue
                    stop_name, stop_lat, stop_lon = stop
                    edge = _resolve_edge(walk_graph, bare_node, ("stop", stop_id), s["lat"], s["lon"], stop_lat, stop_lon, "foot")
                    walk_dur = _walk_duration_sec(edge["distance_m"])
                    total_walk = walk_streak.get(node, 0) + walk_dur
                    if not walk_ok(total_walk):
                        continue
                    relax(("stop", stop_id, None), arrival_sec + walk_dur, {
                        "mode": "walk", "from": [s["lat"], s["lon"]], "to": [stop_lat, stop_lon],
                        "from_name": s["name"], "to_name": stop_name, "dep_sec": arrival_sec, "arr_sec": arrival_sec + walk_dur,
                        "path": edge["geometry"],
                    }, streak=total_walk)

            dest_edge = dest_edges.get(bare_node) if can_end_ride_here else None
            if dest_edge is not None:
                walk_dur = _walk_duration_sec(dest_edge["distance_m"])
                total_walk = walk_streak.get(node, 0) + walk_dur
                if walk_ok(total_walk):
                    relax(DEST, arrival_sec + walk_dur, {
                        "mode": "walk", "from": [s["lat"], s["lon"]], "to": [destination["lat"], destination["lon"]],
                        "from_name": s["name"], "to_name": "Destination", "dep_sec": arrival_sec, "arr_sec": arrival_sec + walk_dur,
                        "path": dest_edge["geometry"],
                    }, streak=total_walk)

    if DEST not in prev and DEST not in dist:
        return None

    raw_legs = []
    node = DEST
    while node in prev:
        parent, leg = prev[node]
        raw_legs.append(leg)
        node = parent
    raw_legs.reverse()

    # WalkGraph.lookup() hands back "path" as a raw numpy array (see its own comment) to
    # avoid a .tolist() conversion on every candidate edge the search considers, most are
    # discarded, not just the ones on the winning route. Convert only here, for the handful
    # of legs that actually made it into the final itinerary. Everything downstream (leg
    # merging, JSON serialization, etc.) expects plain lists.
    for leg in raw_legs:
        path = leg.get("path")
        if isinstance(path, np.ndarray):
            leg["path"] = path.tolist()

    legs = _merge_legs(raw_legs)
    if not legs:
        return None
    legs = _attach_transit_shapes(legs, transit_data)
    legs = _mark_correspondance_walks(legs)
    legs = _mark_station_exit_walks(legs)
    legs = _annotate_bike_risk(legs, bixi_stations)
    legs = _annotate_construction_risk(legs, closure_index)
    legs = _annotate_event_risk(legs, event_index)
    risk_score = compute_risk_score(legs, query_time_sec, transit_data, bixi_stations, active_today, active_yesterday)
    # Must run before _drop_negligible_walk_legs: that function's leading-walk fold blindly
    # adopts the walk leg's dep_sec onto whatever leg follows it (see its own docstring). If
    # the walk is immediately followed by a transit leg with a real scheduled-departure
    # gap (e.g. boarding right as the metro network opens for the day), folding first would
    # silently swallow the whole wait into the transit leg's displayed ride duration instead
    # of surfacing it as its own "wait" leg. Inserting wait legs first turns that gap into a
    # real "wait" leg, so the later fold absorbs the negligible walk into the wait leg
    # (correct) instead of into the transit leg (wrong).
    legs = _insert_wait_legs(legs, transit_data, active_today, active_yesterday)
    legs = _drop_negligible_walk_legs(legs)

    return {
        "departure_sec": query_time_sec,
        "arrival_sec": dist[DEST],
        "duration_sec": dist[DEST] - query_time_sec,
        "risk_score": risk_score,
        "construction_events_count": construction_events_count(legs),
        "legs": legs,
    }


TRANSIT_TYPE_NAMES = {ROUTE_TYPE_BUS: "Bus", ROUTE_TYPE_METRO: "Metro", ROUTE_TYPE_REM: "REM"}


def _dynamic_mode_label(legs):
    """Describes an itinerary by the actual modes it uses (e.g. "Bus + Metro", "REM + BIXI"),
    rather than a generic "Transit" bucket, since riders think in concrete modes, not categories.
    A walk leg only counts toward the label if it survived `_drop_negligible_walk_legs`
    (i.e. is already longer than MIN_DISPLAYED_WALK_LEG_SEC); a trip with only a token walk
    to/from a stop shouldn't read as "X + Walking"."""
    parts = []
    seen = set()
    for leg in legs:
        if leg["mode"] == "transit":
            name = TRANSIT_TYPE_NAMES.get(leg["route_type"], "Transit")
        elif leg["mode"] == "bike":
            name = "BIXI"
        else:
            continue
        if name not in seen:
            seen.add(name)
            parts.append(name)
    if any(leg["mode"] == "walk" for leg in legs):
        parts.append("Walking")
    return " + ".join(parts) if parts else "Walking"


def _leg_signature(legs):
    """Identity of an itinerary's real (non-"wait") legs, used to detect when a mode-
    restricted alternative independently found the exact same route as the unrestricted best:
    two separate Dijkstra runs over the same deterministic graph/cache produce identical leg
    data when they land on the same route, not just a similar one."""
    return tuple(
        (leg["mode"], leg.get("trip_id"), leg.get("bike_type"), leg["dep_sec"], leg["arr_sec"])
        for leg in legs if leg["mode"] != "wait"
    )


def _labeled_alternative(itinerary, fallback_label, unavailable_message):
    if itinerary is None:
        return {"mode_label": fallback_label, "available": False, "message": unavailable_message}
    return {**itinerary, "mode_label": _dynamic_mode_label(itinerary["legs"]), "available": True}


MODE_ROUTE_TYPES = {"bus": ROUTE_TYPE_BUS, "metro": ROUTE_TYPE_METRO, "rem": ROUTE_TYPE_REM}


def _requested_mode_label(route_types, allow_bixi):
    names = [TRANSIT_TYPE_NAMES[rt] for rt in (ROUTE_TYPE_BUS, ROUTE_TYPE_METRO, ROUTE_TYPE_REM) if rt in route_types]
    if allow_bixi:
        names.append("BIXI")
    return " + ".join(names) if names else "Walking"


def plan_trip_alternatives(transit_data, bixi_stations, walk_graph, origin, destination, departure_dt, allow_ebike=False, modes=None, active_closures=None, active_events=None):
    """Up to 7 itineraries: the best route within the rider's selected modes (`modes`, a dict
    like {"bus": True, "metro": True, "rem": True, "bixi": True, "max_walk_minutes": None};
    missing bool keys default to allowed), plus one variant per selected mode with just that
    one mode additionally excluded (all checked -> all-minus-Bus -> all-minus-Metro -> ...),
    plus (if both transit and BIXI are selected) a hybrid variant that caps how long a single
    continuous BIXI ride may be, plus a similar hybrid that caps a single walk leg at
    WALK_LEG_HARD_CAP_SEC, each surfacing a transit-heavier combo as its own alternative when
    that's competitive with a route that leans on one long uninterrupted bike ride or walk.
    `modes["max_walk_minutes"]`, if set, hard-caps every walk leg (access, transfer, and egress
    alike) to that many minutes for every variant; omitted/None means no cap. All restrictions
    are hard graph constraints on the Dijkstra search itself (see _dijkstra_search), not a soft
    weighting or k-shortest-paths search; both are cheaper and more predictable than the
    weighted-strategy diversity approach this project tried and rejected earlier. See
    PHASE6_PLAN.md for the full rationale. Returns None only if even the base (most permissive,
    within your selection) search fails entirely; excluded-mode variants instead come back with
    `"available": False` when that narrower combination can't reach the destination."""
    modes = modes or {}
    base_route_types = frozenset(rt for key, rt in MODE_ROUTE_TYPES.items() if modes.get(key, True))
    base_allow_bixi = modes.get("bixi", True)
    max_walk_minutes = modes.get("max_walk_minutes")
    max_walk_leg_sec = max_walk_minutes * 60 if max_walk_minutes is not None else None

    bixi_index = BixiIndex(bixi_stations)
    ctx = _resolve_dynamic_context(transit_data, bixi_index, bixi_stations, origin, destination, departure_dt)
    closure_index = GeoPointIndex(active_closures) if active_closures else None
    event_index = GeoPointIndex(active_events) if active_events else None

    variants = [{"route_types": base_route_types, "allow_bixi": base_allow_bixi, "excluded": None}]
    for rt in (ROUTE_TYPE_BUS, ROUTE_TYPE_METRO, ROUTE_TYPE_REM):
        if rt in base_route_types:
            variants.append({
                "route_types": base_route_types - {rt}, "allow_bixi": base_allow_bixi,
                "excluded": TRANSIT_TYPE_NAMES[rt], "excluded_route_type": rt, "excluded_bixi": False,
            })
    if base_allow_bixi:
        variants.append({
            "route_types": base_route_types, "allow_bixi": False,
            "excluded": "BIXI", "excluded_route_type": None, "excluded_bixi": True,
        })
    # A hybrid alternative: same modes as the base search, but no single continuous BIXI ride
    # may exceed MAX_HYBRID_BIKE_LEG_SEC. Only meaningful if both transit and BIXI are in play,
    # otherwise there's nothing to hybridize with, or nothing to cap. This is a hard graph
    # constraint like every other variant (see bike_ok in _dijkstra_search), not a soft bias,
    # so it stays an exact search, deliberately not reviving the weighted-strategy "diversity
    # search" this project tried and rejected earlier (see PHASE6_PLAN.md).
    if base_allow_bixi and base_route_types:
        variants.append({
            "route_types": base_route_types, "allow_bixi": True,
            "excluded": "long BIXI rides", "excluded_route_type": None, "excluded_bixi": False,
            "max_bike_leg_sec": MAX_HYBRID_BIKE_LEG_SEC,
        })
    # Same idea again, but for walking: if the winning route leans on one long walk leg (a
    # common way to "win" on paper while being a route few people would actually choose), cap
    # a single walk leg at WALK_LEG_HARD_CAP_SEC and see what transit-heavier combo comes out
    # instead. Only added when that's actually tighter than whatever cap the rider already set
    # via max_walk_minutes, no point offering a "capped" alternative that's looser than what
    # they're already getting.
    if base_route_types and (max_walk_leg_sec is None or WALK_LEG_HARD_CAP_SEC < max_walk_leg_sec):
        variants.append({
            "route_types": base_route_types, "allow_bixi": base_allow_bixi,
            "excluded": "long walks", "excluded_route_type": None, "excluded_bixi": False,
            "max_walk_leg_sec": WALK_LEG_HARD_CAP_SEC,
        })

    def run(variant):
        # MAX_BASE_BIKE_LEG_SEC is the default floor for every variant (no uncapped BIXI
        # streaks, even in mode-exclusion alternatives), the hybrid variant above overrides
        # it with its own stricter MAX_HYBRID_BIKE_LEG_SEC.
        return _dijkstra_search(
            transit_data, bixi_stations, bixi_index, walk_graph, origin, destination, ctx,
            allow_ebike=allow_ebike, allowed_route_types=variant["route_types"],
            allow_bixi=variant["allow_bixi"], max_walk_leg_sec=variant.get("max_walk_leg_sec", max_walk_leg_sec),
            max_bike_leg_sec=variant.get("max_bike_leg_sec", MAX_BASE_BIKE_LEG_SEC),
            closure_index=closure_index, event_index=event_index,
        )

    base_result = run(variants[0])
    if base_result is None:
        return None

    # Dijkstra optimality (see the dedup comment below): a variant that excludes a mode the
    # winning route never used is *guaranteed* to reproduce base_result exactly, so running
    # its own full search would just pay ~11s of CPU-bound (GIL-serialized) Dijkstra work for
    # a result we already have. Skip the search itself, not just its display, this is what
    # actually fixed the ~50s/request regression (5 always-run searches serializing under the
    # GIL); most real trips only use 1-2 of {bus, metro, REM, BIXI}, so this typically leaves
    # only 1-2 extra searches to run instead of 4.
    used_route_types = {leg["route_type"] for leg in base_result["legs"] if leg["mode"] == "transit"}
    used_bixi = any(leg["mode"] == "bike" for leg in base_result["legs"])

    def variant_needed(variant):
        if variant.get("max_bike_leg_sec") is not None:
            # Only worth its own search if the winning route actually has a continuous bike
            # leg long enough for the cap to bite, otherwise it would just reproduce the
            # base result (dedup below handles that anyway, but this skips the search itself).
            return any(
                leg["mode"] == "bike" and (leg["arr_sec"] - leg["dep_sec"]) > variant["max_bike_leg_sec"]
                for leg in base_result["legs"]
            )
        if variant.get("max_walk_leg_sec") is not None:
            return any(
                leg["mode"] == "walk" and (leg["arr_sec"] - leg["dep_sec"]) > variant["max_walk_leg_sec"]
                for leg in base_result["legs"]
            )
        if variant["excluded_bixi"]:
            return used_bixi
        return variant["excluded_route_type"] in used_route_types

    tail_variants = variants[1:]
    needed_idx = [i for i, v in enumerate(tail_variants) if variant_needed(v)]
    results_tail = [base_result] * len(tail_variants)
    if needed_idx:
        to_run = [tail_variants[i] for i in needed_idx]
        with ThreadPoolExecutor(max_workers=len(to_run)) as executor:
            for i, result in zip(needed_idx, executor.map(run, to_run)):
                results_tail[i] = result

    results = [base_result] + results_tail

    seen_signatures = {_leg_signature(results[0]["legs"])}
    labeled = [_labeled_alternative(results[0], _requested_mode_label(variants[0]["route_types"], variants[0]["allow_bixi"]), "No route found for your selected modes.")]
    for variant, result in zip(variants[1:], results[1:]):
        # Excluding a mode the fastest route never used can only ever re-find a route already
        # shown, either the fastest itself (Dijkstra optimality: removing unused edges
        # can't change the optimum), or a route an earlier, less-restricted exclusion variant
        # already surfaced. Skip it instead of listing a redundant duplicate row.
        if result is not None:
            # The BIXI-leg-cap hybrid is only a useful alternative if the cap actually forced
            # a transit leg into the route, otherwise the cheapest way to satisfy "no single
            # bike leg over the cap" is just docking, walking a couple minutes to a different
            # nearby station, and re-renting, which is the same ride from the rider's
            # perspective, not a meaningfully different option worth its own row.
            if variant.get("max_bike_leg_sec") is not None and not any(leg["mode"] == "transit" for leg in result["legs"]):
                continue
            signature = _leg_signature(result["legs"])
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
        fallback_label = _requested_mode_label(variant["route_types"], variant["allow_bixi"])
        unavailable_message = f"No route found without {variant['excluded']}."
        labeled.append(_labeled_alternative(result, fallback_label, unavailable_message))

    return labeled


def _merge_legs(raw_legs):
    """Merge consecutive legs that are really one continuous action: same trip_id transit
    legs (already-existing behavior), and consecutive walk-walk or bike-bike legs, which
    arise because the routing graph is built on stop/BIXI nodes and can pass through one
    without actually boarding/swapping there."""
    merged = []
    for leg in raw_legs:
        same_transit = (
            leg["mode"] == "transit" and merged and merged[-1]["mode"] == "transit"
            and merged[-1]["trip_id"] == leg["trip_id"]
        )
        same_continuous_motion = (
            leg["mode"] in ("walk", "bike") and merged and merged[-1]["mode"] == leg["mode"]
            and merged[-1].get("bike_type") == leg.get("bike_type")
        )

        if same_transit:
            prev_leg = merged[-1]
            prev_leg["to"] = leg["to"]
            prev_leg["to_name"] = leg["to_name"]
            prev_leg["to_stop"] = leg["to_stop"]
            prev_leg["arr_sec"] = leg["arr_sec"]
            prev_leg["path"].append(leg["to"])
            prev_leg["num_stops"] = prev_leg.get("num_stops", 1) + 1
        elif same_continuous_motion:
            prev_leg = merged[-1]
            prev_leg["to"] = leg["to"]
            prev_leg["to_name"] = leg["to_name"]
            prev_leg["arr_sec"] = leg["arr_sec"]
            prev_leg["path"] = prev_leg["path"] + leg["path"][1:]
        else:
            leg = dict(leg)
            if "path" not in leg:
                leg["path"] = [leg["from"], leg["to"]]
            merged.append(leg)
    return merged


def _nearest_shape_index(shape_points, lat, lon):
    d2 = (shape_points[:, 0] - lat) ** 2 + (shape_points[:, 1] - lon) ** 2
    return int(np.argmin(d2))


def _attach_transit_shapes(legs, transit_data):
    """Replaces each (already-merged, one-per-ride) transit leg's straight "connect the visited
    stops" path (set by _merge_legs) with the real GTFS shape polyline when one is available
    (both STM and REM's feeds include shapes.txt). Matters most on routes with a sparse/express
    stretch, where a straight line between two real stops can visibly cut through terrain a bus
    obviously doesn't. Runs once on the final handful of merged legs per itinerary, not during
    the Dijkstra search itself, so it doesn't touch the search's performance."""
    for leg in legs:
        if leg["mode"] != "transit":
            continue
        shape_id = transit_data.trip_shape.get(leg["trip_id"])
        if shape_id is None:
            continue
        shape = transit_data.shapes.get(shape_id)
        if shape is None or len(shape) < 2:
            continue
        start_idx = _nearest_shape_index(shape, leg["from"][0], leg["from"][1])
        end_idx = _nearest_shape_index(shape, leg["to"][0], leg["to"][1])
        if end_idx <= start_idx:
            continue  # out-of-order/degenerate match, keep the straight-line fallback
        leg["path"] = shape[start_idx:end_idx + 1].tolist()
    return legs


def _mark_correspondance_walks(legs):
    """A walk leg sandwiched directly between two transit legs (no real access/egress walk on
    either side) whose straight-line distance is within CORRESPONDANCE_MAX_DISTANCE_M is a
    same-station/short transfer ("correspondance"), not a real walk, see that constant's
    comment for why straight-line distance (not the possibly-inflated routed distance/duration)
    is the right test. Its mode is changed to "correspondance", not removed: its dep_sec/arr_sec/
    path are left untouched so the map can still draw it (same dashed style as a walk leg, see
    map.js's legStyle), but _insert_wait_legs folds its timespan into the following wait leg's
    display instead of giving it its own "Walking" bullet, and compute_risk_score skips over it
    when computing a transit leg's real transfer buffer."""
    for i, leg in enumerate(legs):
        if leg["mode"] != "walk":
            continue
        prev_leg = legs[i - 1] if i > 0 else None
        next_leg = legs[i + 1] if i + 1 < len(legs) else None
        if not (prev_leg and prev_leg["mode"] == "transit" and next_leg and next_leg["mode"] == "transit"):
            continue
        distance_m = haversine_m(leg["from"][0], leg["from"][1], leg["to"][0], leg["to"][1])
        if distance_m <= CORRESPONDANCE_MAX_DISTANCE_M:
            leg["mode"] = "correspondance"
    return legs


def _mark_station_exit_walks(legs):
    """A trailing walk leg with a negligible straight-line distance still carries real time when
    it follows a metro/REM leg: METRO_STATION_EXIT_TIME_SEC (walking up from the platform to
    street level, see weights_config.py) is charged on that edge even when the destination
    point sits right on top of the arrival stop, since _mark_correspondance_walks only folds a
    short walk away when it's sandwiched between two transit legs, never true for the last leg
    of a trip. Flagged here (mode stays "walk" so timing/path handling is untouched) so the
    frontend can render it as a station-exit line instead of a confusing "0 m" walk between two
    identically-named points, see map.js's legTimelineHtml/legDescription."""
    if len(legs) < 2:
        return legs
    last_leg = legs[-1]
    prev_leg = legs[-2]
    if last_leg["mode"] != "walk" or prev_leg["mode"] != "transit":
        return legs
    if prev_leg.get("route_type") not in (ROUTE_TYPE_METRO, ROUTE_TYPE_REM):
        return legs
    distance_m = haversine_m(last_leg["from"][0], last_leg["from"][1], last_leg["to"][0], last_leg["to"][1])
    if distance_m <= CORRESPONDANCE_MAX_DISTANCE_M:
        last_leg["station_exit"] = True
    return legs


def _drop_negligible_walk_legs(legs):
    """Fold walk legs too short to be worth their own itinerary bullet (e.g. "0 min") into
    a neighboring leg instead of displaying them."""
    if len(legs) <= 1:
        return legs

    result = []
    for leg in legs:
        duration = leg["arr_sec"] - leg["dep_sec"]
        if leg["mode"] == "walk" and duration <= MIN_DISPLAYED_WALK_LEG_SEC and result:
            prev_leg = result[-1]
            prev_leg["to"] = leg["to"]
            prev_leg["to_name"] = leg["to_name"]
            prev_leg["arr_sec"] = leg["arr_sec"]
            prev_leg["path"] = prev_leg["path"] + leg["path"][1:]
        else:
            result.append(leg)

    if len(result) > 1:
        first = result[0]
        duration = first["arr_sec"] - first["dep_sec"]
        if first["mode"] == "walk" and duration <= MIN_DISPLAYED_WALK_LEG_SEC:
            second = result[1]
            second["from"] = first["from"]
            second["from_name"] = first["from_name"]
            second["dep_sec"] = first["dep_sec"]
            second["path"] = first["path"][:-1] + second["path"]
            result = result[1:]

    return result


def _insert_wait_legs(legs, transit_data, active_today, active_yesterday):
    """Insert an explicit "wait" leg wherever there's a real gap before a scheduled
    (transit) departure. The time was already counted correctly in duration_sec; this
    just makes it visible as its own itinerary line instead of hiding it inside the
    surrounding legs. When a "correspondance" leg (see _mark_correspondance_walks) sits
    directly before this boarding, the wait leg's span starts from the true previous transit
    leg's arrival, not the correspondance leg's own (possibly street-routing-inflated) arrival,
    so the whole connection shows as one combined "Transfer" bucket in the UI instead of a
    separate short/bogus "Walking" bullet plus an undersized wait."""
    result = []
    for leg in legs:
        if leg["mode"] == "transit" and result:
            prev_leg = result[-1]
            gap_start_leg = result[-2] if prev_leg["mode"] == "correspondance" and len(result) >= 2 else prev_leg
            gap = leg["dep_sec"] - gap_start_leg["arr_sec"]
            if gap > WAIT_LEG_MIN_SEC:
                next_wait_sec = None
                if gap <= WAIT_RISK_WARN_SEC:
                    next_wait_sec = next_same_route_wait_sec(
                        transit_data, leg["from_stop"], leg["route_id"], leg["dep_sec"],
                        active_today, active_yesterday,
                    )
                risk_level, risk_note = _wait_risk(gap, leg.get("transit_label", "your ride"), next_wait_sec)
                result.append({
                    "mode": "wait",
                    "from": prev_leg["to"], "to": prev_leg["to"],
                    "from_name": prev_leg["to_name"], "to_name": prev_leg["to_name"],
                    "dep_sec": gap_start_leg["arr_sec"], "arr_sec": leg["dep_sec"],
                    "path": [prev_leg["to"], prev_leg["to"]],
                    "route_short_name": leg.get("route_short_name"),
                    "transit_label": leg.get("transit_label"), "route_type": leg.get("route_type"),
                    "risk_level": risk_level, "risk_note": risk_note,
                })
        result.append(leg)
    return result


def _next_trip_for_route(transit_data, from_stop_id, to_stop_id, route_id, after_sec, active_today, active_yesterday):
    """Earliest real scheduled departure of a specific route from from_stop_id after after_sec
    that actually reaches to_stop_id, with the real scheduled arrival there, same
    bisect-into-stop_departures + active-service-filter pattern as next_same_route_wait_sec
    (engine/risk.py) and the fresh-boarding candidate loop above, but for a named
    (from_stop, to_stop) pair rather than "whichever stop is next." Returns
    (dep_sec, arr_sec, trip_id), or None if that route doesn't run again within
    PATTERN_LOOKAHEAD_SEC."""
    entries = transit_data.stop_departures.get(from_stop_id)
    if not entries:
        return None
    deps = [e[0] for e in entries]
    idx = _bisect_left(deps, after_sec + 1)
    end_sec = after_sec + PATTERN_LOOKAHEAD_SEC
    for i in range(idx, len(entries)):
        dep_sec, trip_id, idx_in_trip, service_id, day_offset = entries[i]
        if dep_sec > end_sec:
            break
        active_set = active_yesterday if day_offset == 1 else active_today
        if service_id not in active_set:
            continue
        if transit_data.trip_route[trip_id] != route_id:
            continue
        trip_stops = transit_data.trip_stops[trip_id]
        orig_dep_sec = trip_stops[idx_in_trip][2]
        fold = orig_dep_sec - dep_sec if orig_dep_sec != dep_sec else 0
        for j in range(idx_in_trip + 1, len(trip_stops)):
            stop_id, arr_sec, _ = trip_stops[j]
            if stop_id == to_stop_id:
                return dep_sec, arr_sec - fold, trip_id
        # this run doesn't reach to_stop_id (different pattern/direction), keep looking
    return None


def next_departures_for_leg(transit_data, route_id, from_stop_id, to_stop_id, after_sec, active_today, active_yesterday, count=4):
    """The next `count` real scheduled (departure, arrival) times for one specific route
    between one specific stop pair, the right-click "next departures" lookup for a leg
    already on the map. Just repeated calls to _next_trip_for_route, each starting just after
    the previous match's departure; a handful of calls is cheap enough that there's no need for
    next_trip_for_route's own single-match logic to grow a multi-result mode."""
    results = []
    cursor = after_sec
    for _ in range(count):
        found = _next_trip_for_route(transit_data, from_stop_id, to_stop_id, route_id, cursor, active_today, active_yesterday)
        if found is None:
            break
        dep_sec, arr_sec, trip_id = found
        results.append({"dep_sec": dep_sec, "arr_sec": arr_sec, "trip_id": trip_id})
        cursor = dep_sec
    return results


def _interpolated_position(transit_data, trip_id, from_stop_id, to_stop_id):
    """Midpoint of the real shape between two specific consecutive stops on a trip (or a
    straight line between them if no shape is available), the "vehicle hasn't reached the
    next stop yet" placeholder position for modes with no live GPS feed (metro, REM)."""
    _, from_lat, from_lon = transit_data.stops[from_stop_id]
    _, to_lat, to_lon = transit_data.stops[to_stop_id]
    shape_id = transit_data.trip_shape.get(trip_id)
    shape = transit_data.shapes.get(shape_id) if shape_id else None
    if shape is not None and len(shape) >= 2:
        start_idx = _nearest_shape_index(shape, from_lat, from_lon)
        end_idx = _nearest_shape_index(shape, to_lat, to_lon)
        if end_idx > start_idx:
            segment = shape[start_idx:end_idx + 1]
            mid = segment[len(segment) // 2]
            return float(mid[0]), float(mid[1])
    return (from_lat + to_lat) / 2, (from_lon + to_lon) / 2


def estimate_live_vehicle(transit_data, trip_id, now_sec, now_unix, live_gps, live_trip_updates):
    """Best-effort "where is this vehicle, and when does it reach its next stop" for one trip
    on the map right now. Prefers real data, GPS position from STM's vehiclePositions feed
    and a delay-adjusted predicted arrival from its tripUpdates feed (buses only, STM's only
    realtime coverage), and falls back to the static schedule (the real shape's midpoint
    between the two stops `now_sec` falls between, and the plain scheduled arrival time) for
    metro, REM, or a bus not currently reporting live. Returns None if this specific trip isn't
    scheduled to be running at all right now (hasn't started yet / already finished)."""
    trip_stops = transit_data.trip_stops.get(trip_id)
    if not trip_stops or len(trip_stops) < 2:
        return None
    if now_sec < trip_stops[0][1] or now_sec > trip_stops[-1][1]:
        return None

    gps = live_gps.get(trip_id)
    if gps is not None and gps.get("stop_id"):
        lat, lon, source, next_stop_id = gps["lat"], gps["lon"], "gps", gps["stop_id"]
    else:
        lat = lon = next_stop_id = None
        for i in range(len(trip_stops) - 1):
            _, _, dep_sec = trip_stops[i]
            candidate_next_id, next_arr_sec, _ = trip_stops[i + 1]
            if dep_sec <= now_sec <= next_arr_sec:
                lat, lon = _interpolated_position(transit_data, trip_id, trip_stops[i][0], candidate_next_id)
                next_stop_id = candidate_next_id
                break
        if lat is None:
            return None
        source = "schedule"

    next_name = transit_data.stops[next_stop_id][0] if next_stop_id in transit_data.stops else None

    eta_sec = None
    trip_updates = live_trip_updates.get(trip_id)
    if trip_updates and next_stop_id in trip_updates:
        eta_sec = trip_updates[next_stop_id] - now_unix
    else:
        for stop_id, arr_sec, _ in trip_stops:
            if stop_id == next_stop_id:
                eta_sec = arr_sec - now_sec
                break

    return {"trip_id": trip_id, "lat": lat, "lon": lon, "source": source, "next_stop_name": next_name, "eta_sec": eta_sec}


def _resimulate_from(legs, start_index, transit_data, active_today, active_yesterday):
    """After legs[start_index]'s own dep_sec/arr_sec have been finalized (e.g. a rerouted bike
    leg with a new duration), walks the rest of the itinerary forward recomputing real
    dep_sec/arr_sec for every later leg, never adding, removing, or reordering legs. Walk/bike
    legs just follow the new arrival time (their own path/duration is untouched). Transit legs
    are re-validated against the real schedule: if the previously-planned trip is still
    catchable, nothing changes; otherwise the next departure of that same route is looked up via
    _next_trip_for_route and its real times/trip_id replace the old ones. A "wait" leg is
    resolved together with the transit leg it precedes, since its own arr_sec must equal that
    leg's (possibly new) dep_sec. Returns the itinerary's new overall arrival_sec, or None if
    some later transit leg's route doesn't run again today, a real failure, not silently
    ignored."""
    prev_arr = legs[start_index]["arr_sec"]
    i = start_index + 1
    while i < len(legs):
        leg = legs[i]
        if leg["mode"] == "wait":
            transit_leg = legs[i + 1]
            resolved = _resolve_transit_departure(transit_leg, prev_arr, transit_data, active_today, active_yesterday)
            if resolved is None:
                return None
            dep_sec, arr_sec, trip_id = resolved
            leg["dep_sec"] = prev_arr
            leg["arr_sec"] = dep_sec
            transit_leg["dep_sec"] = dep_sec
            transit_leg["arr_sec"] = arr_sec
            transit_leg["trip_id"] = trip_id
            prev_arr = arr_sec
            i += 2
            continue
        if leg["mode"] == "transit":
            resolved = _resolve_transit_departure(leg, prev_arr, transit_data, active_today, active_yesterday)
            if resolved is None:
                return None
            leg["dep_sec"], leg["arr_sec"], leg["trip_id"] = resolved
            prev_arr = leg["arr_sec"]
            i += 1
            continue
        duration = leg["arr_sec"] - leg["dep_sec"]
        leg["dep_sec"] = prev_arr
        leg["arr_sec"] = prev_arr + duration
        prev_arr = leg["arr_sec"]
        i += 1
    return prev_arr


def _resolve_transit_departure(leg, after_sec, transit_data, active_today, active_yesterday):
    if after_sec <= leg["dep_sec"]:
        return leg["dep_sec"], leg["arr_sec"], leg["trip_id"]
    return _next_trip_for_route(
        transit_data, leg["from_stop"], leg["to_stop"], leg["route_id"], after_sec, active_today, active_yesterday,
    )


def reroute_bike_leg(itinerary, leg_index, closure_index, transit_data, active_today, active_yesterday):
    """Reroutes one BIXI leg of an already-planned itinerary around active construction,
    in place, same two stations, same rest of the itinerary, just a different path for that
    one leg and real re-validated times for everything after it. Returns
    (updated_itinerary, None) on success, or (None, reason) if there's nothing to fix or no
    valid alternative exists."""
    legs = itinerary["legs"]
    if not (0 <= leg_index < len(legs)) or legs[leg_index]["mode"] != "bike":
        return None, "leg_index must refer to a BIXI leg."

    detour = find_bike_detour(legs[leg_index], closure_index)
    if detour is None:
        return None, "No alternative route found that clears the closure."
    new_leg, _delta_sec = detour
    legs[leg_index] = new_leg

    final_arrival = _resimulate_from(legs, leg_index, transit_data, active_today, active_yesterday)
    if final_arrival is None:
        return None, "Detour found, but no later scheduled departure exists for a later leg today."

    itinerary["arrival_sec"] = final_arrival
    itinerary["duration_sec"] = final_arrival - itinerary["departure_sec"]
    itinerary["construction_events_count"] = construction_events_count(legs)
    return itinerary, None
