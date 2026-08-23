# services/

This directory contains one thin client module for each external API or data source. Functions here return parsed data or a safe empty fallback (`None`, `{}`, or `[]`) on failure. They do not raise exceptions into `app.py` for routine outages. A briefly unavailable third-party feed should only degrade a specific feature, not break the entire trip planning flow. 

The exception is `google_routes_client.py`, which is allowed to raise errors. It is only used by the `testing/` harness, where a failed live comparison is a useful signal rather than something to hide.

| File | Wired into `app.py`? | Purpose |
|---|---|---|
| `bixi_client.py` | Yes (`/api/bixi_stations`, and consumed by `router.py`) | BIXI bike-share station info and live bikes/docks available via the public GBFS feed. |
| `stm_client.py` | Yes (`/api/next_departures`, `/api/live_vehicles`) | STM GTFS-RT: live bus positions and delay-adjusted arrival predictions. Covers buses only, as the metro lacks a GPS feed. |
| `osrm_client.py` | Indirectly, via `router.py` | Real street and path routes from self-hosted OSRM containers (see `docker-compose.yml`). Returns the single best route and, for hazard avoidance, all available alternative routes. |
| `weather_client.py` | Yes (`/api/plan_trip`'s harsh-weather note) | Current conditions and near-term precipitation chance from Environment Canada's MSC GeoMet API. |
| `construction_client.py` | Yes (`/api/construction`) | Active Montreal road-closure permits from Montreal Open Data. |
| `events_client.py` | Yes (`/api/events`) | Active public events from Montreal Open Data. |
| `geocode_client.py` | Yes (`/api/geocode`) | Address/place search via Nominatim, biased to the Montreal area. |
| `google_routes_client.py` | No (used only by `testing/google_compare.py`) | Google Routes API (TRANSIT mode). Used as an independent oracle to sanity-check itineraries in the validation harness. Never called during real user requests. |

## Why no `rem_client.py` / `elevation_client.py`

Two clients were removed as dead code. The `rem_client.py` file had real code but no call sites, as the REM's live feed was never wired into `app.py`. The `elevation_client.py` stub was abandoned in favor of the offline `engine/elevation.py` (SRTM3 tile lookup). 

If REM realtime integration is needed later, rebuild it using the `stm_client.py` pattern instead of restoring the old file from git history. The GTFS-RT parsing conventions in this codebase have changed significantly since that file was last updated.