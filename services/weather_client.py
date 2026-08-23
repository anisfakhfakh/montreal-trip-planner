import requests

MONTREAL_BBOX = "-73.7,45.4,-73.4,45.6"
CITYPAGE_URL = "https://api.weather.gc.ca/collections/citypageweather-realtime/items"
REQUEST_TIMEOUT_SEC = 10
NEAR_TERM_HOURS = 3


def fetch_current_weather():
    """Current conditions + near-term (next few hours) precipitation chance for Montreal,
    via Environment Canada's MSC GeoMet OGC API (no auth). Returns None on any failure since
    weather should never be a reason to break trip planning."""
    try:
        response = requests.get(
            CITYPAGE_URL,
            params={"bbox": MONTREAL_BBOX, "f": "json", "limit": 1},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        features = response.json().get("features")
        if not features:
            return None
        props = features[0]["properties"]

        # Every leaf value in this API is a bilingual {"en": ..., "fr": ...} dict, even
        # numeric fields like temperature/lop, not a plain scalar.
        current = props.get("currentConditions", {})
        temp_c = current.get("temperature", {}).get("value", {}).get("en")
        condition = current.get("condition", {}).get("en")
        humidity_pct = current.get("relativeHumidity", {}).get("value", {}).get("en")
        dewpoint_c = current.get("dewpoint", {}).get("value", {}).get("en")
        # windChill is only present in the payload when it's cold enough to matter, and is
        # absent (not zero) in warm weather, hence the None default rather than a fallback value.
        windchill_c = current.get("windChill", {}).get("value", {}).get("en")

        hourly = props.get("hourlyForecastGroup", {}).get("hourlyForecasts", [])
        precip_probability_pct = max(
            (h.get("lop", {}).get("value", {}).get("en") or 0 for h in hourly[:NEAR_TERM_HOURS]),
            default=None,
        )

        return {
            "condition": condition,
            "temp_c": float(temp_c) if temp_c is not None else None,
            "humidity_pct": float(humidity_pct) if humidity_pct is not None else None,
            "dewpoint_c": float(dewpoint_c) if dewpoint_c is not None else None,
            "windchill_c": float(windchill_c) if windchill_c is not None else None,
            "precip_probability_pct": precip_probability_pct,
        }
    except Exception:
        return None
