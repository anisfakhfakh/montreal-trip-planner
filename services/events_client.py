from datetime import datetime

import requests

GEOJSON_URL = (
    "https://donnees.montreal.ca/dataset/6a4cbf2c-c9b7-413a-86b1-e8f7081e2578/"
    "resource/35307457-a00f-4912-9941-8095ead51f6e/download/evenements.geojson"
)
REQUEST_TIMEOUT_SEC = 30


def fetch_events():
    """Public events near Montreal, from Montreal Open Data's daily-updated GeoJSON (no auth).
    Informational only, returns [] on any failure, must never break the map or trip
    planning."""
    try:
        response = requests.get(GEOJSON_URL, timeout=REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        features = response.json().get("features", [])
    except Exception:
        return []

    events = []
    for i, feature in enumerate(features):
        props = feature.get("properties", {})
        lat, lon = props.get("lat"), props.get("long")  # dataset field is "long", not "lon"
        if lat is None or lon is None:
            continue
        events.append({
            "id": f"evt-{i}",  # dataset has no natural unique key; stable within one fetch
            "title": props.get("titre"),
            "lat": lat,
            "lon": lon,
            "start_date": props.get("date_debut"),
            "end_date": props.get("date_fin"),
            "location": props.get("emplacement"),
        })
    return events


def is_active_at(event, dt):
    start, end = event.get("start_date"), event.get("end_date")
    if not start or not end:
        return False
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
    except ValueError:
        return False
    return start_date <= dt.date() <= end_date
