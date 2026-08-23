"""BIXI bike-share station data via the public GBFS feed (no auth). Called at request time,
not precomputed, bike/dock availability changes constantly."""
import requests

INFO_URL = "https://gbfs.velobixi.com/gbfs/en/station_information.json"
STATUS_URL = "https://gbfs.velobixi.com/gbfs/en/station_status.json"


def fetch_bixi_stations():
    """Merges station_information (static: name, location, capacity) with station_status
    (live: bikes/docks available) into one dict keyed by station_id. Raises on network
    failure, callers should catch, since BIXI legs can't be offered without this."""
    info = requests.get(INFO_URL, timeout=15).json()["data"]["stations"]
    status = requests.get(STATUS_URL, timeout=15).json()["data"]["stations"]

    status_by_id = {s["station_id"]: s for s in status}

    stations = {}
    for s in info:
        station_id = s["station_id"]
        st = status_by_id.get(station_id)
        if st is None or not st.get("is_installed"):
            continue
        if s["lon"] > -73.0:  # excludes Sherbrooke deployment (~-71.9) on the same GBFS feed
            continue
        stations[station_id] = {
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "capacity": s.get("capacity", 0),
            "bikes_available": st["num_bikes_available"],
            "ebikes_available": st.get("num_ebikes_available", 0),
            "docks_available": st["num_docks_available"],
        }
    return stations
