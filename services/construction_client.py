import io
from datetime import datetime, timezone

import pandas as pd
import requests

CSV_URL = (
    "https://donnees.montreal.ca/dataset/667342f7-f667-4c3c-9837-65e81312cd8d/"
    "resource/cc41b532-f12d-40fb-9f55-eb58c9a2b12b/download/entraves-travaux-en-cours.csv"
)
REQUEST_TIMEOUT_SEC = 30

# Column order matches datetime.weekday() (Monday=0 .. Sunday=6).
_WEEKDAY_ACTIVE_COLUMNS = (
    "duration_days_mon_active", "duration_days_tue_active", "duration_days_wed_active",
    "duration_days_thu_active", "duration_days_fri_active", "duration_days_sat_active",
    "duration_days_sun_active",
)


def fetch_construction_closures():
    """Montreal road-work/closure permits, from Montreal Open Data's daily-updated CSV (no
    auth). Every row in this feed already represents an issued/in-progress permit, there is
    no "cancelled"/"completed" status value to filter on, only the date range + weekday-active
    flags (see is_active_at). Returns [] on any failure, a fetch outage must never break
    trip planning."""
    try:
        response = requests.get(CSV_URL, timeout=REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), dtype=str)
    except Exception:
        return []

    closures = []
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (TypeError, ValueError):
            continue
        closures.append({
            "id": row["id"],
            "lat": lat,
            "lon": lon,
            "reason": row.get("reason_category") or "Construction",
            "occupancy": row.get("occupancy_name"),
            "start_date": row.get("duration_start_date"),
            "end_date": row.get("duration_end_date"),
            "active_weekdays": [row.get(col) == "t" for col in _WEEKDAY_ACTIVE_COLUMNS],
        })
    return closures


def is_active_at(closure, dt):
    """Date range + that weekday's active flag only, v1 skips hourly precision (the
    per-weekday start/end time columns), which the source data rarely populates anyway."""
    start, end = closure.get("start_date"), closure.get("end_date")
    if not start or not end:
        return False
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return False
    dt_aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if not (start_dt <= dt_aware <= end_dt):
        return False
    return closure["active_weekdays"][dt_aware.weekday()]
