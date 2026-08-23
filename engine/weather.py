import math

from engine.weights_config import (
    HUMIDEX_DISCOMFORT_THRESHOLD,
    SEVERE_PRECIP_KEYWORDS,
    WINDCHILL_DISCOMFORT_THRESHOLD_C,
)


def compute_humidex(temp_c, dewpoint_c):
    """Environment Canada's official humidex formula (feels-like heat) from real temperature
    + dewpoint, both already in the currentConditions payload services/weather_client.py
    fetches, so no extra data source needed."""
    if temp_c is None or dewpoint_c is None:
        return None
    vapor_pressure_hpa = 6.11 * math.exp(5417.7530 * (1 / 273.16 - 1 / (273.16 + dewpoint_c)))
    return temp_c + 0.5555 * (vapor_pressure_hpa - 10)


def classify_harsh_weather(weather):
    """Whether right-now weather is uncomfortable enough to warn a rider exposed to it on a
    walk/BIXI leg, and a short plain-language reason why. A boolean trigger, not a numeric
    discomfort score, by explicit design choice, see PHASE8_PLAN.md. Cold side: Environment
    Canada's own windchill comfort scale. Hot side: their humidex scale. Precipitation: a
    keyword match against the current condition text. Returns harsh=False (never raises, never
    blocks trip planning) if weather data isn't available at all."""
    if not weather:
        return {"available": False, "harsh": False, "reason": None, "condition": None, "temp_c": None}

    reasons = []

    windchill_c = weather.get("windchill_c")
    if windchill_c is not None and windchill_c <= WINDCHILL_DISCOMFORT_THRESHOLD_C:
        reasons.append(f"feels like {windchill_c:.0f}°C (windchill)")

    humidex = compute_humidex(weather.get("temp_c"), weather.get("dewpoint_c"))
    if humidex is not None and humidex >= HUMIDEX_DISCOMFORT_THRESHOLD:
        reasons.append(f"feels like {humidex:.0f}°C (humidex, high humidity)")

    condition = weather.get("condition") or ""
    if any(keyword in condition.lower() for keyword in SEVERE_PRECIP_KEYWORDS):
        reasons.append(condition)

    return {
        "available": True,
        "harsh": bool(reasons),
        "reason": " and ".join(reasons) if reasons else None,
        "condition": weather.get("condition"),
        "temp_c": weather.get("temp_c"),
    }
