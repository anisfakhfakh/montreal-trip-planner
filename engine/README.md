# Engine README

The deterministic routing and scoring core. Everything here is pure Python + precomputed data. No live external API calls happen inside a search itself (those are all resolved once, up front,
by `_resolve_dynamic_context`, and cached data is read from `services/` clients and precomputed
caches). See
[ROUTING_ALGORITHM.md](../ROUTING_ALGORITHM.md) at the repo root. Here we present the the file/function
index.

| File | Purpose |
|---|---|
| `router.py` | The whole multi-modal trip planner: `_dijkstra_search` (the ripple/shortest-path search itself), `_resolve_dynamic_context` (live OSRM calls for the user's exact click points), leg merge/cleanup (`_merge_legs`, `_mark_correspondance_walks`, `_attach_transit_shapes`, `_insert_wait_legs`), `plan_trip_alternatives` (reruns the search with different mode combinations to produce different alternatives), plus live-vehicle estimation and single-leg BIXI rerouting. |
| `graph_builder.py` | Parses the STM + REM static GTFS zips into a `TransitData` object (stop spots, per-stop sorted departure lists, day-type resolution) and pickles it to `data/raw/transit_cache.pkl` so the app never re-parses GTFS at request time. |
| `weights_config.py` | Single source of truth for every tunable constant walking and BIXI speeds, penalties, thresholds. |
| `risk.py` | The itinerary risk-score model: starts at 0, adds a penalty per risk factor (low BIXI dock availability, a tight transfer buffer, the cost of missing the next scheduled departure), normalized by leg count. Replaced an earlier 100-start-subtract model that users found too opaque to act on. |
| `weather.py` | Uses Environment Canada's temperature and humidex/windchill information for Informational purposes only not blocking trip planning. |
| `walk_graph.py` | Loads and queries the precomputed walk/bike edge + neighbor-list cache (`data/raw/walk_graph_cache.pkl`, built by `data/scripts/precompute_walk_graph.py`). |
| `data_refresh.py` | Admin-triggered background refresh jobs (rebuild the BIXI walk-graph cache, re-download + rebuild the STM schedule). Each runs as a real subprocess — not in-process — so the ~10-15 minute OSRM-heavy rebuild never competes with Flask's own GIL for live search requests, and a crash in the job can't take the app down. |
| `elevation.py` | Local SRTM3 `.hgt` tile lookup for hill ascend/descend on bike legs. Only used offline by `data/scripts/precompute_walk_graph.py` — never at request time, so a missing tile degrades gracefully (bike legs just assume flat) rather than breaking trip planning. |

## Data flow at a glance

```
data/scripts/*.py (offline, one-off or admin-triggered)
        |
        v
data/raw/*.pkl caches  --loaded at app startup by-->  graph_builder.py / walk_graph.py
        |
        v
router.py's _dijkstra_search (reads the caches + live services/ data, computes an itinerary)
        |
        v
risk.py / weather.py (annotate the itinerary with risk flags / a harsh-weather note)
```
