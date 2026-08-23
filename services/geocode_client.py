import requests

SEARCH_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a descriptive User-Agent identifying the app (not a
# spoofed browser string), same constraint as the STM GTFS download's WAF, see
# data/scripts/download_gtfs.py.
USER_AGENT = "MontrealTripPlanner/1.0 (personal project; contact: github.com/anisfakhfakh/montreal-trip-planner)"
# Greater Montreal area (island + Laval + South Shore), used to bias results toward local
# addresses without excluding legitimate matches just outside the box (soft bias, not bounded=1).
MONTREAL_VIEWBOX = "-74.05,45.85,-73.20,45.30"


def geocode(query, limit=5, viewbox=None, bounded=True):
    """Forward-geocodes a free-text address/place query via Nominatim, biased to Montreal.
    Returns a list of {"name", "lat", "lon", "address"} candidates, best match first. Raises
    on network/HTTP failure, callers should catch, since the search bar can't function
    without this."""
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": limit,
        "viewbox": viewbox or MONTREAL_VIEWBOX,
        "addressdetails": 1,
    }
    if bounded:
        params["bounded"] = 1
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(SEARCH_URL, params=params, headers=headers, timeout=10)
    response.raise_for_status()

    return [
        {
            "name": r["display_name"],
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            # Structured components (house_number/road/postcode) let the frontend build a
            # short "123 Rue Example W, H3B 5L1" label instead of Nominatim's full display_name.
            # Only present when Nominatim actually resolved them (e.g. not for a landmark-only
            # match), so callers must handle missing fields.
            "address": {
                "house_number": r.get("address", {}).get("house_number"),
                "road": r.get("address", {}).get("road"),
                "postcode": r.get("address", {}).get("postcode"),
            },
        }
        for r in response.json()
    ]
