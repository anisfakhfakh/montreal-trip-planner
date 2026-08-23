import os

import requests
from google.transit import gtfs_realtime_pb2

STM_GTFS_RT_BASE = "https://api.stm.info/pub/od/gtfs-rt/ic/v2"
REQUEST_TIMEOUT_SEC = 15


def _fetch_feed(path):
    api_key = os.getenv("STM_API_KEY")
    if not api_key:
        return None
    try:
        response = requests.get(
            f"{STM_GTFS_RT_BASE}/{path}",
            headers={"apiKey": api_key, "accept": "application/x-protobuf"},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        return feed
    except Exception:
        return None


def fetch_stm_vehicle_positions():
    """Live bus GPS positions, keyed by trip_id (prefixed "STM:" to match this project's id
    scheme). STM's realtime feed only covers buses, metro has no GPS feed, REM isn't STM's.
    Returns {} on any failure (missing/invalid key, network error, malformed response), a
    realtime outage must never break trip planning, which only needs the static schedule."""
    feed = _fetch_feed("vehiclePositions")
    if feed is None:
        return {}
    positions = {}
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        vehicle = entity.vehicle
        trip_id = vehicle.trip.trip_id
        if not trip_id or not vehicle.HasField("position"):
            continue
        positions["STM:" + trip_id] = {
            "lat": vehicle.position.latitude,
            "lon": vehicle.position.longitude,
            "stop_id": "STM:" + vehicle.stop_id if vehicle.stop_id else None,
            "timestamp": vehicle.timestamp,
        }
    return positions


def fetch_stm_trip_updates():
    """Live, delay-adjusted predicted arrival times: trip_id -> {stop_id: predicted_unix_sec}.
    Same bus-only coverage as fetch_stm_vehicle_positions. Returns {} on any failure."""
    feed = _fetch_feed("tripUpdates")
    if feed is None:
        return {}
    updates = {}
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update
        trip_id = trip_update.trip.trip_id
        if not trip_id:
            continue
        stop_times = {}
        for stu in trip_update.stop_time_update:
            if stu.HasField("arrival") and stu.arrival.time:
                stop_times["STM:" + stu.stop_id] = stu.arrival.time
        updates["STM:" + trip_id] = stop_times
    return updates
