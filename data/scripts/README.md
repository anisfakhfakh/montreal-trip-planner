# data/scripts/

Offline and one-off ETL scripts used to populate `data/raw/` (see [data/README.md](../README.md)). These never run during a user request. The application only reads the caches and files they produce.

| Script | When it runs | Purpose |
|---|---|---|
| `download_gtfs.py` | Manually, or as a step inside `refresh_stm.py` | Downloads the STM and REM static GTFS zips. Handles the STM's edge WAF, which otherwise returns an HTML error page if requested without a `Referer` header from their own site. |
| `refresh_stm.py` | Invoked as a subprocess by `engine/data_refresh.py`'s admin-triggered "Refresh STM schedule" job | Re-downloads the STM's GTFS zip and rebuilds `transit_cache.pkl`. Designed to be run as a script, not imported. |
| `precompute_elevation.py` | Manually, once during initial setup | Downloads the single SRTM3 tile covering the app's entire service area. |
| `precompute_walk_graph.py` | Manually, or invoked as a subprocess by `engine/data_refresh.py`'s admin-triggered "Refresh BIXI network" job | This is the slowest script. It resolves every stop-to-stop, stop-to-BIXI, and BIXI-to-BIXI pair within a relevant radius to a real OSRM route, calculating elevation-derived ascent and descent. The results are written to `walk_graph_cache.pkl`. This precomputation allows the live Dijkstra search in `engine/router.py` to avoid calling OSRM or reading the elevation tile during actual requests. |

Note: Two originally planned scripts, such as `build_demand_model.py`, were never written and existed only as empty stubs. They have been removed as dead code rather than kept as placeholders.