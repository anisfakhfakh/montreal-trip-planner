"""Risk-score model for transit itineraries: starts at 0, adds a penalty point per risk
factor (BIXI dock availability, tight transit transfers, cost of missing the next
departure), normalized by leg count. Replaces the old 100-start-subtract probability.py
model, which users found too opaque/inaccurate to act on."""

from bisect import bisect_left

from engine.weights_config import (
    BIXI_PLENTY_THRESHOLD,
    PATTERN_LOOKAHEAD_SEC,
    RISK_BIXI_FEW_PENALTY,
    RISK_BIXI_NONE_PENALTY,
    RISK_NEXT_DEPARTURE_UNDER_15MIN_PENALTY,
    RISK_NEXT_DEPARTURE_UNDER_30MIN_PENALTY,
    RISK_NEXT_DEPARTURE_UNDER_45MIN_PENALTY,
    RISK_NEXT_DEPARTURE_OVER_45MIN_PENALTY,
    RISK_TRANSIT_BUFFER_DANGER_PENALTY,
    RISK_TRANSIT_BUFFER_DANGER_SEC,
    RISK_TRANSIT_BUFFER_WARN_PENALTY,
    RISK_TRANSIT_BUFFER_WARN_SEC,
)


def _bike_leg_penalty(leg, bixi_stations):
    station = bixi_stations.get(leg.get("from_stop_id"))
    if station is None:
        return 0
    ebikes = station.get("ebikes_available", 0)
    is_electric = leg.get("bike_type") == "electric"
    count = ebikes if is_electric else max(station.get("bikes_available", 0) - ebikes, 0)
    if count == 0:
        return RISK_BIXI_NONE_PENALTY
    if count < BIXI_PLENTY_THRESHOLD:
        return RISK_BIXI_FEW_PENALTY
    return 0


def next_same_route_wait_sec(transit_data, stop_id, route_id, after_sec, active_today, active_yesterday):
    """Seconds until the next scheduled departure of the same route from this stop, after
    the one actually taken, "if you miss this one, how long are you stuck." None if
    nothing found within the lookahead window (treated as the worst bucket by the caller)."""
    entries = transit_data.stop_departures.get(stop_id)
    if not entries:
        return None
    deps = [e[0] for e in entries]
    idx = bisect_left(deps, after_sec + 1)
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
        return dep_sec - after_sec
    return None


def _missed_departure_penalty(wait_sec):
    if wait_sec is None or wait_sec >= 45 * 60:
        return RISK_NEXT_DEPARTURE_OVER_45MIN_PENALTY
    if wait_sec >= 30 * 60:
        return RISK_NEXT_DEPARTURE_UNDER_45MIN_PENALTY
    if wait_sec >= 15 * 60:
        return RISK_NEXT_DEPARTURE_UNDER_30MIN_PENALTY
    return RISK_NEXT_DEPARTURE_UNDER_15MIN_PENALTY


def _transit_leg_penalty(leg, prev_arr_sec, transit_data, active_today, active_yesterday):
    buffer_sec = leg["dep_sec"] - prev_arr_sec
    if buffer_sec <= RISK_TRANSIT_BUFFER_DANGER_SEC:
        penalty = RISK_TRANSIT_BUFFER_DANGER_PENALTY
    elif buffer_sec < RISK_TRANSIT_BUFFER_WARN_SEC:
        penalty = RISK_TRANSIT_BUFFER_WARN_PENALTY
    else:
        return 0

    wait_sec = next_same_route_wait_sec(
        transit_data, leg["from_stop"], leg["route_id"], leg["dep_sec"], active_today, active_yesterday,
    )
    return penalty + _missed_departure_penalty(wait_sec)


def compute_risk_score(legs, query_time_sec, transit_data, bixi_stations, active_today, active_yesterday):
    """Aggregate risk score for an itinerary: 0 = no risk factors triggered, higher = more.
    Summed penalty points normalized by the number of transport legs (transit + bike) only, since
    walking isn't a "risk" leg, so a trip with a long access walk shouldn't read as safer just
    for having more total legs. A "correspondance" leg (see engine/router.py's
    _mark_correspondance_walks) never advances prev_arr_sec, its own timespan can be inflated
    by street-level routing standing in for a short in-station transfer, and letting that eat
    into the buffer used below would understate a transit leg's real connection time."""
    if not legs:
        return 0.0

    total = 0
    transport_leg_count = 0
    prev_arr_sec = query_time_sec
    for leg in legs:
        if leg["mode"] == "bike":
            total += _bike_leg_penalty(leg, bixi_stations)
            transport_leg_count += 1
        elif leg["mode"] == "transit":
            total += _transit_leg_penalty(leg, prev_arr_sec, transit_data, active_today, active_yesterday)
            transport_leg_count += 1
        if leg["mode"] != "correspondance":
            prev_arr_sec = leg["arr_sec"]

    return total / transport_leg_count if transport_leg_count else 0.0
