"""Batch-runs the routes in routes.json against a live /api/plan_trip and writes a results
JSON that the Route Validation Log dashboard can import (its "Import script results" button),
so the Trip Planner side of that log never has to be typed in by hand. This is a 3-way
comparison per route, not a single "Google" figure, see testing/google_compare.py's module
docstring:
  1. appTime/appModes/etc, this app's own planner (always run).
  2. gTransit*, a live Google Routes API TRANSIT query (--with-google only, costs a real API
     call; GOOGLE_MAPS_ROUTES_API_KEY in .env), restricted to the route's allowed bus/metro/rem
     subset. Never includes bixi, Google's developer API has no bikeshare mode. gTransitLegs
     carries a leg-by-leg breakdown (incl. explicit "wait" legs) alongside the total. gTransitLink
     is a clickable Google Maps transit-directions URL, generated regardless of --with-google (no
     API cost), note it always opens departing "now", Google's URL API has no exact-time param,
     so it's a best-effort click-through, not a like-for-like reproduction of gTransitTime.
  3. gBixiLink, a clickable Google Maps bicycling-directions URL, generated whenever the
     route's allowedModes permits bixi (always, no API cost). There's no API for Google's
     bike-share integration, so click through and read the numbers off manually.
Manual entry in the artifact is still available as a fallback/override for all of the above.

The dashboard's source lives at testing/route_validation_log.html (edit and redeploy it
manually to update it in place), its embedded ROUTES array mirrors routes.json (incl.
allowedModes) by hand, keep both in sync if routes.json changes.

Usage:
    python testing/validate_routes.py                      # run everything, default times
    python testing/validate_routes.py --ids 6,14,35         # just a few routes
    python testing/validate_routes.py --list                # print the route table and exit
    python testing/validate_routes.py --departure-time 2026-08-12T08:00  # force one time for all
    python testing/validate_routes.py --base-url http://localhost:5000 --out testing/results/run1.json
    python testing/validate_routes.py --ids 6,14 --with-google  # also live-query Google Transit

Requires the Flask dev server (app.py) already running and reachable at --base-url.
--with-google requires GOOGLE_MAPS_ROUTES_API_KEY in .env (see services/google_routes_client.py).
gBixiLink is generated regardless of --with-google (no API call needed for a plain URL).
"""
import argparse
import json
import math
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.weights_config import WALK_LEG_HARD_CAP_SEC
from google_compare import bixi_maps_link, resolve_google_transit, transit_maps_link

ROUTES_PATH = Path(__file__).parent / "routes.json"
RESULTS_DIR = Path(__file__).parent / "results"

ROUTE_TYPE_NAMES = {0: "REM", 1: "Metro", 3: "Bus"}
SKIP_LEG_MODES = {"wait", "correspondance", "station_exit"}

EARTH_RADIUS_M = 6371000


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    to_rad = math.radians
    d_lat, d_lon = to_rad(lat2 - lat1), to_rad(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def leg_distance_m(leg: dict) -> float:
    """No distance_m field ships on legs (see engine/router.py), sum the real routed path
    instead, exactly like map.js's legDistanceMeters() does for the on-screen leg list."""
    path = leg.get("path") or []
    return sum(haversine_m(*path[i - 1], *path[i]) for i in range(1, len(path)))


def format_distance(meters: float) -> str:
    return f"{meters / 1000:.1f} km" if meters > 1000 else f"{round(meters)} m"


def format_clock(total_seconds) -> str | None:
    """Mirrors map.js's formatClock, dep_sec/arr_sec are seconds since local midnight
    (and can exceed 86400 for a leg that folds past midnight), so wrap into a 24h clock."""
    if total_seconds is None:
        return None
    secs = int(total_seconds) % 86400
    return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}"


def leg_label(leg: dict) -> str:
    """Mirrors map.js's legDescription labelling, so the leg-by-leg breakdown reads the same
    as what a rider sees in the app itself."""
    mode = leg.get("mode")
    if mode == "walk":
        return "Exit to street" if leg.get("station_exit") else "Walk"
    if mode == "correspondance":
        return "Transfer"
    if mode == "wait":
        return f"Wait for {leg.get('transit_label') or 'transit'}"
    if mode == "bike":
        return "E-BIXI" if leg.get("bike_type") == "electric" else "BIXI"
    if mode == "transit":
        return leg.get("transit_label") or ROUTE_TYPE_NAMES.get(leg.get("route_type"), "Transit")
    return mode or "?"


def leg_details(itinerary: dict) -> list[dict]:
    """One row per leg (from/to name, departure, arrival, elapsed minutes) for the Route
    Validation Log's leg-by-leg table, the full itinerary, not the collapsed mode summary
    summarize_itinerary() produces."""
    rows = []
    for leg in itinerary.get("legs", []):
        dep_sec, arr_sec = leg.get("dep_sec"), leg.get("arr_sec")
        elapsed = round((arr_sec - dep_sec) / 60, 1) if dep_sec is not None and arr_sec is not None else None
        rows.append({
            "mode": leg.get("mode"),
            "label": leg_label(leg),
            "from": leg.get("from_name"),
            "to": leg.get("to_name"),
            "departure": format_clock(dep_sec),
            "arrival": format_clock(arr_sec),
            "elapsedMin": elapsed,
            "distance": format_distance(leg_distance_m(leg)),
        })
    return rows


def load_routes():
    data = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    return data["routes"]


def next_departure(default_time: str, day_type: str, now: datetime) -> datetime:
    """Mirrors the artifact's own JS default-time logic, so an unfilled departure time in the
    UI and a fresh script run land on the same kind of moment (next matching HH:MM)."""
    hh, mm = (int(x) for x in default_time.split(":"))
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    if day_type == "weekday":
        while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
            candidate += timedelta(days=1)
    elif day_type == "weekend":
        while candidate.weekday() < 5:
            candidate += timedelta(days=1)
    return candidate


def summarize_itinerary(itinerary: dict) -> dict:
    """Derives the same three fields a human would read off the app's UI: total time, a
    transfer count, and a collapsed mode sequence. Transfers = (number of transit/bike rides
    - 1); walk/wait/correspondance/station_exit legs don't count as rides. This is a proxy,
    not the app's own definition, good enough to compare against a Google Maps read, not
    meant to be exact to the leg."""
    legs = itinerary.get("legs", [])
    # Each mode appears once, in order of first occurrence, with duration summed across every
    # (not just consecutive) leg of that mode, e.g. two separate bus rides with a transfer
    # in between still show as a single "Bus" chip, not "Bus, Bus".
    order = []
    totals = {}
    ride_count = 0
    for leg in legs:
        mode = leg.get("mode")
        if mode in SKIP_LEG_MODES:
            continue
        dep_sec, arr_sec = leg.get("dep_sec"), leg.get("arr_sec")
        duration = (arr_sec - dep_sec) if dep_sec is not None and arr_sec is not None else 0
        if mode == "walk":
            label = "Walk"
        elif mode == "bike":
            label = "E-BIXI" if leg.get("bike_type") == "electric" else "BIXI"
            ride_count += 1
        elif mode == "transit":
            label = ROUTE_TYPE_NAMES.get(leg.get("route_type"), "Transit")
            ride_count += 1
        else:
            label = mode
        if label not in totals:
            totals[label] = 0
            order.append(label)
        totals[label] += duration
    # A Walk entry only counts as "a mode" in this summary if it clears the same 5-minute bar
    # the app itself uses to call a walk leg significant (WALK_LEG_HARD_CAP_SEC, the "Walking
    # (5+ minutes)" toggle), otherwise it's just getting to/from a stop, not worth a chip.
    # Exception: a walking-only itinerary (the trip's one and only leg) always keeps its Walk.
    if len(order) > 1:
        order = [label for label in order if label != "Walk" or totals[label] > WALK_LEG_HARD_CAP_SEC]
    modes = order
    total_distance_m = sum(leg_distance_m(leg) for leg in legs)
    return {
        "appTime": round(itinerary.get("duration_sec", 0) / 60, 1),
        "appTransfers": max(0, ride_count - 1),
        "appModes": modes,
        "appLegs": leg_details(itinerary),
        "appDistance": format_distance(total_distance_m),
    }


DEFAULT_MODES = {"bus": True, "metro": True, "rem": True, "bixi": True, "max_walk_minutes": None}
BOOL_MODE_KEYS = ("bus", "metro", "rem", "bixi")


def run_route(base_url: str, route: dict, departure_dt: datetime, allow_ebike: bool, timeout: float):
    body = {
        "origin": route["origin"],
        "destination": route["destination"],
        "departure_time": departure_dt.strftime("%Y-%m-%dT%H:%M:00"),
        "allow_ebike": allow_ebike,
        "modes": route.get("allowedModes", DEFAULT_MODES),
    }
    start = time.time()
    try:
        resp = requests.post(f"{base_url}/api/plan_trip", json=body, timeout=timeout)
    except requests.RequestException as exc:
        return {"error": f"request failed: {exc}", "elapsedSec": round(time.time() - start, 2)}

    elapsed = round(time.time() - start, 2)

    if resp.status_code != 200:
        try:
            detail = resp.json().get("error", resp.text)
        except ValueError:
            detail = resp.text
        return {"error": f"HTTP {resp.status_code}: {detail}", "elapsedSec": elapsed}

    payload = resp.json()
    itineraries = payload.get("itineraries") or []
    if not itineraries:
        return {"error": "no itineraries returned", "elapsedSec": elapsed}

    result = summarize_itinerary(itineraries[0])
    result["error"] = None
    result["elapsedSec"] = elapsed
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:5000")
    parser.add_argument("--ids", help="comma-separated route ids to run (default: all)")
    parser.add_argument("--departure-time", help="ISO datetime (YYYY-MM-DDTHH:MM) to force for every selected route, overriding each route's own default-time/day-type")
    parser.add_argument("--allow-ebike", action="store_true", help="allow e-bikes in every search (route #24 is meant to test this)")
    parser.add_argument("--timeout", type=float, default=180.0, help="per-request timeout in seconds (cross-island searches can legitimately take 30-90s)")
    parser.add_argument("--out", help="output path (default: testing/results/app_results_<timestamp>.json)")
    parser.add_argument("--list", action="store_true", help="print the route table and exit without calling the API")
    parser.add_argument("--with-google", action="store_true", help="also live-query Google Maps (Routes API) for a gTime/gModes/etc. comparison, costs a real API call per route, see services/google_routes_client.py")
    args = parser.parse_args()

    routes = load_routes()
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",")}
        routes = [r for r in routes if r["id"] in wanted]
        if not routes:
            sys.exit(f"No routes matched --ids {args.ids}")

    if args.list:
        for r in routes:
            print(f"#{r['id']:>2}  {r['from']} -> {r['to']}  [{', '.join(r['tags'])}]  default {r['defaultTime']} ({r['dayType']})")
        return

    forced_dt = datetime.fromisoformat(args.departure_time) if args.departure_time else None
    now = datetime.now()

    results = []
    print(f"Running {len(routes)} route(s) against {args.base_url} ...\n")
    for i, r in enumerate(routes, 1):
        dep_dt = forced_dt or next_departure(r["defaultTime"], r["dayType"], now)
        modes = r.get("allowedModes", DEFAULT_MODES)
        bool_modes = {k: modes.get(k, True) for k in BOOL_MODE_KEYS}
        walk_cap = modes.get("max_walk_minutes")
        note_bits = []
        if not all(bool_modes.values()):
            note_bits.append(', '.join(m for m, on in bool_modes.items() if on))
        if walk_cap is not None:
            note_bits.append(f"walk<={walk_cap}min")
        modes_note = f" [{'; '.join(note_bits)}]" if note_bits else ""
        print(f"[{i}/{len(routes)}] #{r['id']} {r['from']} -> {r['to']}{modes_note}  (departing {dep_dt.strftime('%Y-%m-%d %H:%M')}) ...", end=" ", flush=True)
        outcome = run_route(args.base_url, r, dep_dt, args.allow_ebike, args.timeout)
        outcome["id"] = r["id"]
        outcome["departureTime"] = dep_dt.strftime("%Y-%m-%dT%H:%M")
        outcome["gBixiLink"] = bixi_maps_link(r)
        outcome["gTransitLink"] = transit_maps_link(r)
        if args.with_google:
            outcome.update(resolve_google_transit(r, dep_dt))
        results.append(outcome)
        if outcome.get("error"):
            print(f"FAILED ({outcome['elapsedSec']}s): {outcome['error']}")
        else:
            print(f"{outcome['appTime']} min, {outcome['appTransfers']} transfer(s), {' -> '.join(outcome['appModes'])}  [{outcome['elapsedSec']}s]", end="")
        if args.with_google:
            if outcome.get("gTransitTime") is not None:
                print(f"  | Google Transit: {outcome['gTransitTime']} min, {' -> '.join(outcome['gTransitModes'])}")
            else:
                print(f"  | Google Transit: no appropriate route found{' (' + outcome['gTransitError'] + ')' if outcome.get('gTransitError') else ''}")
        elif not outcome.get("error"):
            print()
        if outcome.get("gBixiLink"):
            print(f"  | Google BIXI: {outcome['gBixiLink']}")

    out_path = Path(args.out) if args.out else RESULTS_DIR / f"app_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    failed = sum(1 for r in results if r.get("error"))
    total_elapsed = sum(r["elapsedSec"] for r in results)
    avg_elapsed = total_elapsed / len(results) if results else 0
    print(f"\n{len(results) - failed}/{len(results)} succeeded. Wrote {out_path}")
    print(f"Total request time: {total_elapsed:.1f}s, average: {avg_elapsed:.1f}s/route")
    if failed:
        print(f"{failed} route(s) failed, see \"error\" fields in the output file")


if __name__ == "__main__":
    main()
