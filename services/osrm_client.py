import requests
from requests.adapters import HTTPAdapter

OSRM_BASE_URLS = {
    "foot": "http://localhost:5001",
    "bike": "http://localhost:5002",
}

# Pooled connections so high-volume callers (the walk-graph precompute script, which fires
# tens of thousands of requests from a thread pool) don't re-handshake TCP per call.
_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32)
_session.mount("http://", _adapter)


def osrm_route(lat1, lon1, lat2, lon2, mode):
    """Fetch a real street/path route between two points from the local OSRM server.

    mode is "foot" or "bike". Returns {"distance_m": float, "geometry": [[lat, lon], ...]},
    or None on any failure (container not running, timeout, malformed response), callers
    should fall back to haversine distance when this returns None.
    """
    base_url = OSRM_BASE_URLS[mode]
    url = f"{base_url}/route/v1/{mode}/{lon1},{lat1};{lon2},{lat2}"
    params = {"overview": "full", "geometries": "geojson"}

    try:
        response = _session.get(url, params=params, timeout=2)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return None

        route = data["routes"][0]
        coordinates = route["geometry"]["coordinates"]

        return {
            "distance_m": route["distance"],
            "geometry": [[lat, lon] for lon, lat in coordinates],
        }
    except Exception:
        return None


def osrm_route_alternatives(lat1, lon1, lat2, lon2, mode):
    """Same request as osrm_route, but asks OSRM for every alternative route it can find
    (not just the best one) so a caller can pick one that avoids a specific hazard point.
    Returns a list of {"distance_m", "geometry"} (possibly just one entry, or [] on any
    failure), OSRM doesn't guarantee more than one route exists for a given pair."""
    base_url = OSRM_BASE_URLS[mode]
    url = f"{base_url}/route/v1/{mode}/{lon1},{lat1};{lon2},{lat2}"
    params = {"overview": "full", "geometries": "geojson", "alternatives": "true"}

    try:
        response = _session.get(url, params=params, timeout=3)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return []

        return [
            {
                "distance_m": route["distance"],
                "geometry": [[lat, lon] for lon, lat in route["geometry"]["coordinates"]],
            }
            for route in data["routes"]
        ]
    except Exception:
        return []
