"""Live "Google Maps" comparison for one routes.json entry, used by validate_routes.py's
--with-google flag. This is a 3-way comparison, not a merge into one "Google" figure:

  1. appTime/appModes/etc (validate_routes.py's own run_route()), this app's own planner,
     using the route's actual allowedModes (bus/metro/rem/bixi combined as configured).
  2. gTransit* (resolve_google_transit, below), a real Google Routes API TRANSIT query,
     restricted to this route's allowed bus/metro/rem subset (never bixi, Google's developer
     API has no bikeshare/dock-aware mode at all, only the consumer Maps app/website does, in
     select cities). Attempted whenever at least one of bus/metro/rem is allowed, independent of
     whether bixi is also allowed.
  3. gBixiLink (bixi_maps_link, below), a plain Google Maps bicycling-directions URL for this
     route's origin/destination, generated only when this route's allowedModes permits bixi.
     There's no API for Google's bike-share integration, so this can't be resolved to a number
     automatically, click through and read off whatever Google shows. No API call/cost, so
     this is always computed regardless of --with-google.

Google's transitPreferences.allowedTravelModes is NOT a hard filter in practice (verified
empirically 2026-08-14, a request restricted to allowedTravelModes=["BUS"] still returned
alternatives containing a REM/TRAM leg), and Google's transit API has no walk-time-cap
parameter at all. Both constraints are enforced here instead, client-side, by requesting
alternative routes and scanning each one's steps.
"""
from datetime import timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from services.google_routes_client import (
    fetch_transit_alternatives,
    REM_VEHICLE_TYPE,
    STM_BUS_VEHICLE_TYPE,
    STM_METRO_VEHICLE_TYPE,
)

MONTREAL_TZ = ZoneInfo("America/Montreal")
WALK_LEG_HARD_CAP_SEC = 300  # mirrors engine.weights_config.WALK_LEG_HARD_CAP_SEC / summarize_itinerary()'s bar

MODE_VEHICLE_TYPES = {
    "bus": STM_BUS_VEHICLE_TYPE,
    "metro": STM_METRO_VEHICLE_TYPE,
    "rem": REM_VEHICLE_TYPE,
}
VEHICLE_TYPE_TO_LABEL = {
    STM_BUS_VEHICLE_TYPE: "Bus",
    STM_METRO_VEHICLE_TYPE: "Metro",
    REM_VEHICLE_TYPE: "REM",
}


def _format_distance(meters: float) -> str:
    return f"{meters / 1000:.1f} km" if meters > 1000 else f"{round(meters)} m"


def _format_clock_local(dt_utc) -> str:
    return dt_utc.astimezone(MONTREAL_TZ).strftime("%H:%M")


def _leg_label(leg: dict) -> str:
    vt_label = VEHICLE_TYPE_TO_LABEL.get(leg.get("vehicle_type"), leg.get("vehicle_type") or "transit")
    name_suffix = f" {leg['line_name']}" if leg.get("line_name") else ""
    if leg["mode"] == "walk":
        return "Walk"
    if leg["mode"] == "wait":
        return f"Wait for {vt_label}{name_suffix}"
    return f"{vt_label}{name_suffix}"


def _display_legs(raw_legs: list[dict]) -> list[dict]:
    """Formats _build_legs' raw UTC-datetime legs (services/google_routes_client.py) into the
    same shape testing/validate_routes.py's leg_details() produces for the Trip Planner side, so
    both render through the same legs table in the artifact."""
    rows = []
    for leg in raw_legs:
        elapsed = round((leg["arrival"] - leg["departure"]).total_seconds() / 60, 1)
        rows.append({
            "mode": leg["mode"],
            "label": _leg_label(leg),
            "from": leg["from"],
            "to": leg["to"],
            "departure": _format_clock_local(leg["departure"]),
            "arrival": _format_clock_local(leg["arrival"]),
            "elapsedMin": elapsed,
            "distance": _format_distance(leg["distance_m"]),
        })
    return rows


def _alternative_is_valid(route, allowed_modes, max_walk_minutes):
    disallowed_vehicle_types = {
        vt for mode, vt in MODE_VEHICLE_TYPES.items() if not allowed_modes.get(mode, True)
    }
    max_walk_sec = max_walk_minutes * 60 if max_walk_minutes else None
    for step in route["steps"]:
        if step["travel_mode"] == "WALK":
            if max_walk_sec is not None and step["duration_sec"] > max_walk_sec:
                return False
        elif step["vehicle_type"] in disallowed_vehicle_types:
            return False
    return True


def _collapse_modes(steps):
    # Each mode appears once, in order of first occurrence, with duration summed across every
    # (not just consecutive) leg of that mode, e.g. two separate bus rides with a transfer
    # in between still show as a single "Bus" chip, not "Bus, Bus".
    order = []
    totals = {}
    for step in steps:
        if step["travel_mode"] == "WALK":
            label = "Walk"
        else:
            label = VEHICLE_TYPE_TO_LABEL.get(step["vehicle_type"], step["vehicle_type"] or "Transit")
        if label not in totals:
            totals[label] = 0
            order.append(label)
        totals[label] += step["duration_sec"]
    if len(order) > 1:
        order = [label for label in order if label != "Walk" or totals[label] > WALK_LEG_HARD_CAP_SEC]
    return order


def bixi_maps_link(route: dict) -> str | None:
    """Clickable Google Maps bicycling-directions URL for this route's origin/destination, or
    None if this route's allowedModes doesn't permit bixi. Pure URL construction, no API call.
    Google's bike-share integration (where it shows a BIXI option) only exists in the consumer
    Maps UI, so this is the closest thing to an automated "Google BIXI" comparison without
    scraping (see module docstring)."""
    modes = route.get("allowedModes", {"bixi": True})
    if not modes.get("bixi", True):
        return None
    origin, destination = route["origin"], route["destination"]
    params = {
        "api": 1,
        "origin": f"{origin['lat']},{origin['lon']}",
        "destination": f"{destination['lat']},{destination['lon']}",
        "travelmode": "bicycling",
    }
    return f"https://www.google.com/maps/dir/?{urlencode(params)}"


def transit_maps_link(route: dict) -> str | None:
    """Clickable Google Maps *transit*-directions URL for this route's origin/destination, or
    None if no transit mode is allowed for this route. Pure URL construction, no API call.

    Google's public Maps URL API (developers.google.com/maps/documentation/urls) has no parameter
    for an exact departure date/time, opening this link always shows directions departing "now",
    not the date/time this route was actually tested at. The artifact surfaces that caveat next to
    the link; gTransitTime/gTransitLegs (from resolve_google_transit, above) are what actually
    reflect the tested date/time and should be treated as the real comparison figures."""
    modes = route.get("allowedModes", {"bus": True, "metro": True, "rem": True})
    if not (modes.get("bus", True) or modes.get("metro", True) or modes.get("rem", True)):
        return None
    origin, destination = route["origin"], route["destination"]
    params = {
        "api": 1,
        "origin": f"{origin['lat']},{origin['lon']}",
        "destination": f"{destination['lat']},{destination['lon']}",
        "travelmode": "transit",
    }
    return f"https://www.google.com/maps/dir/?{urlencode(params)}"


def resolve_google_transit(route, departure_dt_local):
    """Best (min-duration) Google TRANSIT alternative that satisfies both this route's
    allowed bus/metro/rem subset and its max_walk_minutes cap, gTransitTime/gTransitTransfers/
    gTransitModes/gTransitDistance/gTransitLegs are None/empty (with gTransitError set) if no
    alternative qualifies, no transit mode is allowed for this route at all, or the live call
    itself fails."""
    modes = route.get("allowedModes", {"bus": True, "metro": True, "rem": True, "max_walk_minutes": None})
    max_walk_minutes = modes.get("max_walk_minutes")
    empty = {"gTransitTime": None, "gTransitTransfers": None, "gTransitModes": [], "gTransitDistance": None, "gTransitLegs": []}

    if not (modes.get("bus", True) or modes.get("metro", True) or modes.get("rem", True)):
        return {**empty, "gTransitError": "no transit mode allowed for this route"}

    departure_dt_utc = departure_dt_local.replace(tzinfo=MONTREAL_TZ).astimezone(timezone.utc)
    try:
        alternatives = fetch_transit_alternatives(route["origin"], route["destination"], departure_dt_utc)
    except Exception as exc:
        return {**empty, "gTransitError": str(exc)}

    valid = [alt for alt in alternatives if _alternative_is_valid(alt, modes, max_walk_minutes)]
    if not valid:
        return empty

    best = min(valid, key=lambda alt: alt["duration_sec"])
    ride_count = sum(1 for s in best["steps"] if s["travel_mode"] != "WALK")
    return {
        "gTransitTime": round(best["duration_sec"] / 60, 1),
        "gTransitTransfers": max(0, ride_count - 1),
        "gTransitModes": _collapse_modes(best["steps"]),
        "gTransitDistance": _format_distance(best["distance_m"]),
        "gTransitLegs": _display_legs(best["legs"]),
    }
