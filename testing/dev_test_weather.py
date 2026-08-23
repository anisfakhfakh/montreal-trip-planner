"""Dev-only helper: runs the real app with weather forced to a chosen scenario, so the
harsh-weather UI (note + "Consider another weather-friendly route?" button) can be seen live
in a real browser without waiting for actual bad weather. Not part of the app, safe to
delete once you're done testing.

Usage (from the repo root):
    python testing/dev_test_weather.py [blizzard|heatwave|deepfreeze|heavyrain|mild]

Then open http://localhost:5000 and plan a real trip as usual.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_module

SCENARIOS = {
    "blizzard": {"condition": "Blizzard", "temp_c": -10.0, "humidity_pct": 90, "dewpoint_c": -12.0, "windchill_c": -22.0, "precip_probability_pct": 90},
    "heatwave": {"condition": "Sunny", "temp_c": 34.0, "humidity_pct": 85, "dewpoint_c": 26.0, "windchill_c": None, "precip_probability_pct": 0},
    "deepfreeze": {"condition": "Clear", "temp_c": -18.0, "humidity_pct": 70, "dewpoint_c": -22.0, "windchill_c": -28.0, "precip_probability_pct": 5},
    "heavyrain": {"condition": "Heavy Rain", "temp_c": 12.0, "humidity_pct": 95, "dewpoint_c": 11.0, "windchill_c": None, "precip_probability_pct": 95},
    "mild": {"condition": "Mainly Clear", "temp_c": 18.0, "humidity_pct": 60, "dewpoint_c": 10.0, "windchill_c": None, "precip_probability_pct": 10},
}

scenario_name = sys.argv[1] if len(sys.argv) > 1 else "blizzard"
weather = SCENARIOS[scenario_name]
app_module.get_weather = lambda: weather
print(f"[dev_test_weather] forcing scenario '{scenario_name}': {weather}")

if __name__ == "__main__":
    app_module.app.run(debug=True)
