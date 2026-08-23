import os
import pickle
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CACHE_PATH = RAW_DIR / "transit_cache.pkl"

FEEDS = {
    "STM": RAW_DIR / "stm_gtfs.zip",
    "REM": RAW_DIR / "rem_gtfs.zip",
}

EARTH_RADIUS_M = 6371000


def _seconds_from_hms(series):
    parts = series.str.split(":", expand=True).astype("int32")
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _load_feed(zip_path, prefix):
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("stops.txt") as f:
            stops = pd.read_csv(f, usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"], dtype={"stop_id": str}, encoding="utf-8-sig")
        with zf.open("routes.txt") as f:
            routes = pd.read_csv(
                f,
                usecols=["route_id", "route_short_name", "route_long_name", "route_type", "route_color", "route_text_color"],
                dtype={"route_id": str, "route_color": str, "route_text_color": str},
                encoding="utf-8-sig",
            )
        with zf.open("trips.txt") as f:
            trips = pd.read_csv(f, usecols=["trip_id", "route_id", "service_id", "shape_id", "trip_headsign"], dtype=str, encoding="utf-8-sig")
        with zf.open("stop_times.txt") as f:
            stop_times = pd.read_csv(
                f,
                usecols=["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"],
                dtype={"trip_id": str, "stop_id": str, "stop_sequence": "int32"},
                encoding="utf-8-sig",
            )
        with zf.open("calendar.txt") as f:
            calendar = pd.read_csv(f, dtype=str, encoding="utf-8-sig")
        try:
            with zf.open("calendar_dates.txt") as f:
                calendar_dates = pd.read_csv(f, dtype=str, encoding="utf-8-sig")
        except KeyError:
            calendar_dates = pd.DataFrame(columns=["service_id", "date", "exception_type"])
        try:
            with zf.open("shapes.txt") as f:
                shapes = pd.read_csv(
                    f,
                    usecols=["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
                    dtype={"shape_id": str}, encoding="utf-8-sig",
                )
        except KeyError:
            shapes = pd.DataFrame(columns=["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"])

    for df, cols in ((stops, ["stop_id"]), (routes, ["route_id"]), (trips, ["trip_id", "route_id", "service_id"]),
                      (stop_times, ["trip_id", "stop_id"]), (calendar, ["service_id"]), (calendar_dates, ["service_id"]),
                      (shapes, ["shape_id"])):
        for col in cols:
            df[col] = prefix + ":" + df[col]
    # shape_id is optional per GTFS spec, some trips legitimately have none (blank in the
    # source data); only prefix the ones that exist so a missing shape stays missing, not a
    # dangling "PREFIX:nan" that would never match a real shapes_df row.
    has_shape = trips["shape_id"].notna()
    trips.loc[has_shape, "shape_id"] = prefix + ":" + trips.loc[has_shape, "shape_id"]

    stop_times["arrival_sec"] = _seconds_from_hms(stop_times["arrival_time"])
    stop_times["departure_sec"] = _seconds_from_hms(stop_times["departure_time"])

    return stops, routes, trips, stop_times, calendar, calendar_dates, shapes


class TransitData:
    def __init__(self, stops, routes, trip_route, trip_headsign, trip_stops, stop_departures, service_calendar, service_exceptions, stop_routes, shapes, trip_shape):
        self.stops = stops  # stop_id -> (name, lat, lon)
        self.routes = routes  # route_id -> (short_name, long_name, color, text_color, route_type)
        self.trip_route = trip_route  # trip_id -> route_id
        self.trip_headsign = trip_headsign  # trip_id -> GTFS trip_headsign string (may be missing/NaN)
        self.trip_stops = trip_stops  # trip_id -> list of (stop_id, arr_sec, dep_sec)
        self.stop_departures = stop_departures  # stop_id -> sorted list of (dep_sec, trip_id, idx_in_trip, service_id, day_offset)
        self.service_calendar = service_calendar  # service_id -> (weekday_bools, start_date_int, end_date_int)
        self.service_exceptions = service_exceptions  # service_id -> {date_int: exception_type}
        self.stop_routes = stop_routes  # stop_id -> set of route_id serving that stop
        self.shapes = shapes  # shape_id -> float32 ndarray of [lat, lon], in travel order
        self.trip_shape = trip_shape  # trip_id -> shape_id (missing if the trip has none)

        self.stop_ids = np.array(list(stops.keys()))
        self.stop_lats = np.array([stops[s][1] for s in self.stop_ids])
        self.stop_lons = np.array([stops[s][2] for s in self.stop_ids])

    def active_service_ids(self, on_date):
        date_int = int(on_date.strftime("%Y%m%d"))
        weekday = on_date.weekday()  # 0=Monday
        active = set()
        for service_id, (weekday_bools, start_date, end_date) in self.service_calendar.items():
            if start_date <= date_int <= end_date and weekday_bools[weekday]:
                active.add(service_id)
        for service_id, exceptions in self.service_exceptions.items():
            exc = exceptions.get(date_int)
            if exc == 1:
                active.add(service_id)
            elif exc == 2:
                active.discard(service_id)
        return active

    def nearby_stops(self, lat, lon, radius_m):
        lat1, lat2 = np.radians(lat), np.radians(self.stop_lats)
        dlat = lat2 - lat1
        dlon = np.radians(self.stop_lons - lon)
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        distances = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
        mask = distances <= radius_m
        return list(zip(self.stop_ids[mask], distances[mask]))


def _build_service_calendar(calendar_df):
    result = {}
    weekday_cols = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for row in calendar_df.itertuples(index=False):
        weekday_bools = tuple(getattr(row, col) == "1" for col in weekday_cols)
        result[row.service_id] = (weekday_bools, int(row.start_date), int(row.end_date))
    return result


def _build_service_exceptions(calendar_dates_df):
    result = {}
    for row in calendar_dates_df.itertuples(index=False):
        result.setdefault(row.service_id, {})[int(row.date)] = int(row.exception_type)
    return result


def _build_trip_stops_and_departures(stop_times_df, trips_df):
    df = stop_times_df.sort_values(["trip_id", "stop_sequence"], kind="stable").reset_index(drop=True)
    df["idx_in_trip"] = df.groupby("trip_id", sort=False).cumcount()

    trip_codes, trip_uniques = pd.factorize(df["trip_id"], sort=False)
    change_idx = np.nonzero(np.diff(trip_codes))[0] + 1
    stop_id_groups = np.split(df["stop_id"].values, change_idx)
    arr_groups = np.split(df["arrival_sec"].values, change_idx)
    dep_groups = np.split(df["departure_sec"].values, change_idx)

    trip_stops = {
        trip_uniques[i]: list(zip(stop_id_groups[i], arr_groups[i].tolist(), dep_groups[i].tolist()))
        for i in range(len(trip_uniques))
    }

    trip_service = dict(zip(trips_df["trip_id"], trips_df["service_id"]))
    df["service_id"] = df["trip_id"].map(trip_service)

    stop_departures = {}
    for stop_id, group in df.groupby("stop_id", sort=False):
        entries = list(zip(group["departure_sec"], group["trip_id"], group["idx_in_trip"], group["service_id"], [0] * len(group)))
        overflow = group[group["departure_sec"] >= 86400]
        if not overflow.empty:
            entries += list(zip(
                overflow["departure_sec"] - 86400, overflow["trip_id"], overflow["idx_in_trip"], overflow["service_id"], [1] * len(overflow)
            ))
        entries.sort(key=lambda e: e[0])
        stop_departures[stop_id] = entries

    return trip_stops, stop_departures


def _build_shapes(shapes_df):
    """shape_id -> ordered [[lat, lon], ...] polyline (the real vehicle path, from GTFS
    shapes.txt), sorted by shape_pt_sequence. Stored as float32 arrays, same rationale as the
    precomputed walk graph's geometry: compact, fast to unpickle, plenty of precision for
    display."""
    if shapes_df.empty:
        return {}
    df = shapes_df.sort_values(["shape_id", "shape_pt_sequence"], kind="stable")
    result = {}
    for shape_id, group in df.groupby("shape_id", sort=False):
        result[shape_id] = np.array(
            list(zip(group["shape_pt_lat"].astype("float32"), group["shape_pt_lon"].astype("float32")))
        )
    return result


def _build_stop_routes(stop_times_df, trips_df):
    pairs = stop_times_df[["trip_id", "stop_id"]].drop_duplicates().merge(
        trips_df[["trip_id", "route_id"]], on="trip_id"
    )
    return pairs.groupby("stop_id")["route_id"].apply(set).to_dict()


def _build(force=False):
    if not force and CACHE_PATH.exists():
        newest_source = max(p.stat().st_mtime for p in FEEDS.values())
        if CACHE_PATH.stat().st_mtime >= newest_source:
            with open(CACHE_PATH, "rb") as f:
                return pickle.load(f)

    all_stops, all_routes, all_trips, all_stop_times, all_calendar, all_calendar_dates, all_shapes = [], [], [], [], [], [], []
    for prefix, zip_path in FEEDS.items():
        stops, routes, trips, stop_times, calendar, calendar_dates, shapes = _load_feed(zip_path, prefix)
        all_stops.append(stops)
        all_routes.append(routes)
        all_trips.append(trips)
        all_stop_times.append(stop_times)
        all_calendar.append(calendar)
        all_calendar_dates.append(calendar_dates)
        all_shapes.append(shapes)

    stops_df = pd.concat(all_stops, ignore_index=True)
    routes_df = pd.concat(all_routes, ignore_index=True)
    trips_df = pd.concat(all_trips, ignore_index=True)
    stop_times_df = pd.concat(all_stop_times, ignore_index=True)
    calendar_df = pd.concat(all_calendar, ignore_index=True)
    calendar_dates_df = pd.concat(all_calendar_dates, ignore_index=True)
    shapes_df = pd.concat(all_shapes, ignore_index=True)

    stops = {
        row.stop_id: (row.stop_name, float(row.stop_lat), float(row.stop_lon))
        for row in stops_df.itertuples(index=False)
    }
    routes = {
        row.route_id: (row.route_short_name, row.route_long_name, row.route_color, row.route_text_color, int(row.route_type))
        for row in routes_df.itertuples(index=False)
    }
    trip_route = dict(zip(trips_df["trip_id"], trips_df["route_id"]))
    trip_headsign = dict(zip(trips_df["trip_id"], trips_df["trip_headsign"]))
    trip_shape = dict(zip(trips_df.loc[trips_df["shape_id"].notna(), "trip_id"], trips_df.loc[trips_df["shape_id"].notna(), "shape_id"]))

    trip_stops, stop_departures = _build_trip_stops_and_departures(stop_times_df, trips_df)
    service_calendar = _build_service_calendar(calendar_df)
    service_exceptions = _build_service_exceptions(calendar_dates_df)
    stop_routes = _build_stop_routes(stop_times_df, trips_df)
    shapes = _build_shapes(shapes_df)

    transit_data = TransitData(
        stops, routes, trip_route, trip_headsign, trip_stops, stop_departures, service_calendar, service_exceptions,
        stop_routes, shapes, trip_shape,
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # Write-then-rename instead of a direct open(CACHE_PATH, "wb"), os.replace is atomic on both
    # Windows and POSIX, so a reader (or a second concurrent refresh job racing on this same path)
    # only ever sees the old complete file or the new complete file, never a partial write.
    tmp_path = CACHE_PATH.with_suffix(f"{CACHE_PATH.suffix}.tmp{os.getpid()}")
    with open(tmp_path, "wb") as f:
        pickle.dump(transit_data, f)
    os.replace(tmp_path, CACHE_PATH)

    return transit_data


def build_transit_data(force=False):
    return _build(force=force)


if __name__ == "__main__":
    data = build_transit_data(force=True)
    print(f"stops: {len(data.stops)}, routes: {len(data.routes)}, trips: {len(data.trip_stops)}")
    today_active = data.active_service_ids(date.today())
    print(f"services active today: {len(today_active)}")
