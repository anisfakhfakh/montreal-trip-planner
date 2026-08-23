"""Offline builder for walk_graph_cache.pkl: every stop<->stop, stop<->BIXI, and BIXI<->BIXI
pair within the relevant radius (see engine/weights_config.py), each resolved to a real OSRM
street/path route + elevation-derived ascend/descend, so the live Dijkstra search
(engine/router.py) never has to call OSRM or the elevation tile at request time. Slow (OSRM +
elevation lookups over tens of thousands of pairs via a thread pool), run manually
(`python data/scripts/precompute_walk_graph.py`) or via the admin "Refresh BIXI network" button
(engine/data_refresh.py), whenever the BIXI station layout changes materially."""
import os
import pickle
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine.elevation import elevation_m
from engine.graph_builder import build_transit_data
from engine.router import BixiIndex, haversine_m
from engine.weights_config import BIXI_ACCESS_RADIUS_M, BIXI_RIDE_RADIUS_M, TRANSFER_WALK_RADIUS_M
from services.bixi_client import fetch_bixi_stations
from services.osrm_client import osrm_route

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"
CACHE_PATH = RAW_DIR / "walk_graph_cache.pkl"

MAX_WORKERS = 32

SAMPLE_INTERVAL_M = 50
# Segment classified "flat" if |net elevation change| is within this band, SRTM3's own
# vertical noise (~6-9m RMSE per published SRTM accuracy assessments) would otherwise produce
# spurious ascend/descend classification on genuinely flat ground.
GRADE_DEADBAND_M = 4


def _resample_polyline(geometry, interval_m=SAMPLE_INTERVAL_M):
    """geometry: list of [lat, lon] vertices in path order (an OSRM route). Returns points
    resampled at ~interval_m intervals along the path via cumulative haversine distance +
    linear lat/lon interpolation between the bracketing original vertices. Always includes the
    first and last original vertex."""
    if len(geometry) < 2:
        return list(geometry)

    cum = [0.0]
    for i in range(1, len(geometry)):
        lat1, lon1 = geometry[i - 1]
        lat2, lon2 = geometry[i]
        cum.append(cum[-1] + haversine_m(lat1, lon1, lat2, lon2))
    total = cum[-1]
    if total == 0:
        return [geometry[0], geometry[-1]]

    n_intervals = max(int(total // interval_m), 1)
    targets = [i * interval_m for i in range(n_intervals + 1)]
    if targets[-1] < total:
        targets.append(total)

    samples = []
    seg_idx = 0
    for target in targets:
        while seg_idx < len(cum) - 2 and cum[seg_idx + 1] < target:
            seg_idx += 1
        seg_start, seg_end = cum[seg_idx], cum[seg_idx + 1]
        seg_len = seg_end - seg_start
        t = 0.0 if seg_len == 0 else (target - seg_start) / seg_len
        lat1, lon1 = geometry[seg_idx]
        lat2, lon2 = geometry[seg_idx + 1]
        samples.append([lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)])
    return samples


def _grade_profile(geometry):
    """Returns (ascend_m, descend_m): meters of the route's own path DISTANCE (not vertical
    height) classified net-ascending / net-descending, using GRADE_DEADBAND_M per resampled
    segment. ascend_m + descend_m + "flat" distance sums to the total route distance, matching
    how engine/router.py's _bike_duration_sec consumes them."""
    samples = _resample_polyline(geometry)
    elevations = [elevation_m(lat, lon) for lat, lon in samples]

    ascend_m = 0.0
    descend_m = 0.0
    for i in range(1, len(samples)):
        seg_dist = haversine_m(samples[i - 1][0], samples[i - 1][1], samples[i][0], samples[i][1])
        delta_h = elevations[i] - elevations[i - 1]
        if delta_h > GRADE_DEADBAND_M:
            ascend_m += seg_dist
        elif delta_h < -GRADE_DEADBAND_M:
            descend_m += seg_dist
        # else within the dead-band: counted as flat, added to neither
    return ascend_m, descend_m


def _stop_stop_pairs(transit_data):
    for stop_id in transit_data.stop_ids:
        _, lat, lon = transit_data.stops[stop_id]
        for other_id, _ in transit_data.nearby_stops(lat, lon, TRANSFER_WALK_RADIUS_M):
            if other_id == stop_id:
                continue
            _, other_lat, other_lon = transit_data.stops[other_id]
            yield ("stop", stop_id), ("stop", other_id), "foot", lat, lon, other_lat, other_lon


def _stop_bixi_pairs(transit_data, bixi_index, bixi_stations):
    for stop_id in transit_data.stop_ids:
        _, lat, lon = transit_data.stops[stop_id]
        for station_id, _ in bixi_index.nearby(lat, lon, BIXI_ACCESS_RADIUS_M):
            s = bixi_stations[station_id]
            yield ("stop", stop_id), ("bixi", station_id), "foot", lat, lon, s["lat"], s["lon"]


def _bixi_stop_pairs(transit_data, bixi_index, bixi_stations):
    for station_id in bixi_index.ids:
        s = bixi_stations[station_id]
        for stop_id, _ in transit_data.nearby_stops(s["lat"], s["lon"], TRANSFER_WALK_RADIUS_M):
            _, lat, lon = transit_data.stops[stop_id]
            yield ("bixi", station_id), ("stop", stop_id), "foot", s["lat"], s["lon"], lat, lon


def _bixi_bixi_pairs(bixi_index, bixi_stations):
    for station_id in bixi_index.ids:
        s = bixi_stations[station_id]
        for other_id, _ in bixi_index.nearby(s["lat"], s["lon"], BIXI_RIDE_RADIUS_M):
            if other_id == station_id:
                continue
            other = bixi_stations[other_id]
            yield ("bixi", station_id), ("bixi", other_id), "bike", s["lat"], s["lon"], other["lat"], other["lon"]


def _resolve(pair):
    from_node, to_node, mode, lat1, lon1, lat2, lon2 = pair
    result = osrm_route(lat1, lon1, lat2, lon2, mode)
    if result is not None and mode == "bike":
        ascend_m, descend_m = _grade_profile(result["geometry"])
        result = {**result, "ascend_m": ascend_m, "descend_m": descend_m}
    return from_node, to_node, mode, result


def build_walk_graph():
    print("Loading transit data + live BIXI stations...")
    transit_data = build_transit_data()
    bixi_stations = fetch_bixi_stations()
    bixi_index = BixiIndex(bixi_stations)

    print("Enumerating candidate pairs (stop<->stop, stop<->BIXI, BIXI<->BIXI)...")
    pairs = (
        list(_stop_stop_pairs(transit_data))
        + list(_stop_bixi_pairs(transit_data, bixi_index, bixi_stations))
        + list(_bixi_stop_pairs(transit_data, bixi_index, bixi_stations))
        + list(_bixi_bixi_pairs(bixi_index, bixi_stations))
    )
    print(f"{len(pairs)} directed pairs to resolve via local OSRM")

    print("Grouping neighbor lists by starting waypoint...")
    neighbors = {}
    for from_node, to_node, mode, *_ in pairs:
        neighbors.setdefault((from_node, mode), []).append(to_node)

    cache = {}
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_resolve, pair) for pair in pairs]
        for i, future in enumerate(as_completed(futures), 1):
            from_node, to_node, mode, result = future.result()
            if result is not None:
                # geometry stored as a compact float32 array, unpickles far faster at app
                # startup than the equivalent Python list-of-lists across ~400k cache entries
                entry = {
                    "distance_m": result["distance_m"],
                    "geometry": np.array(result["geometry"], dtype=np.float32),
                }
                if "ascend_m" in result:
                    entry["ascend_m"] = result["ascend_m"]
                    entry["descend_m"] = result["descend_m"]
                cache[(from_node, to_node, mode)] = entry
            else:
                failed += 1
            if i % 5000 == 0:
                print(f"  {i}/{len(pairs)} resolved ({failed} failed so far)")

    print(f"Done: {len(cache)} pairs cached, {failed} failed (those fall back to haversine at query time).")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # Write-then-rename instead of a direct open(CACHE_PATH, "wb"), os.replace is atomic on both
    # Windows and POSIX, so a reader (or a second concurrent refresh job racing on this same path)
    # only ever sees the old complete file or the new complete file, never a partial write.
    tmp_path = CACHE_PATH.with_suffix(f"{CACHE_PATH.suffix}.tmp{os.getpid()}")
    with open(tmp_path, "wb") as f:
        pickle.dump({"edges": cache, "neighbors": neighbors}, f)
    os.replace(tmp_path, CACHE_PATH)
    print(f"Wrote cache to {CACHE_PATH}")


if __name__ == "__main__":
    build_walk_graph()
