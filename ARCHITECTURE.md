# Architecture

This is the current-state reference for the codebase. It details what each part does, how the backend, frontend, and algorithmic pieces divide up, and why the app is structured this way. For setup and run instructions, see the root [README.md](README.md). For a code-free walkthrough of the routing algorithm, see [ROUTING_ALGORITHM.md](ROUTING_ALGORITHM.md).

## 1. What the app does

A trip planner for Montreal that combines transit (STM bus/metro, REM light rail), BIXI bike-share, and walking into a single itinerary search. Users can plan a trip from any point in the city to another, optionally restricting modes or capping walking time. The system ranks results by duration, number of legs, and risk score, and displays active construction and events. It also provides live bus positions, next-departure lookups, and single-leg rerouting around active construction.

## 2. Directory map

| Directory | Role | Details |
|---|---|---|
| `engine/` | Backend: Deterministic routing and scoring core | [engine/README.md](engine/README.md) |
| `services/` | Backend: One client per external API | [services/README.md](services/README.md) |
| `data/` | Backend: Generated/downloaded data and the pipeline that builds it | [data/README.md](data/README.md) |
| `static/`, `templates/` | Frontend | [static/README.md](static/README.md), [templates/README.md](templates/README.md) |
| `testing/` | Route-validation harness | [testing/README.md](testing/README.md) |
| `app.py`, `config.py` | Flask entry point and `.env` config loading | See §3 below |

## 3. Backend

`app.py` is a single Flask app with no blueprints or app factory. This matches the app's scale: it operates as a single process with a single purpose. At import time, it validates the config and builds `transit_data` (parsed GTFS via `engine/graph_builder.py`) and `walk_graph` (precomputed walk/bike distances via `engine/walk_graph.py`) as module-level globals. It then derives the metro/REM station list and the service-area bounds from `transit_data`.

**In-memory caching, not a database.** `transit_data` and `walk_graph` are loaded once at startup from pickled files in `data/raw/` and read directly from process memory on every request. There is no database in this application. Live external data (BIXI availability, weather, STM realtime, construction/events) is cached in simple module-level dictionaries with per-source TTLs. These refresh lazily on the next request past the TTL rather than on a background timer. This fits a single-instance deployment perfectly. If the app ever scales to multiple worker processes, this cache would need to move to a shared store like Redis.

**Two admin-triggered refresh jobs** (`engine/data_refresh.py`) rebuild the on-disk caches without restarting the app. They handle redownloading the STM schedule and rebuilding the BIXI walk-graph cache. Each runs as a distinct subprocess so the heavy OSRM rebuild never competes with Flask's GIL for live search requests. They are guarded by a cross-process file lock. On success, the job's callback reloads the fresh pickle into the running process's memory.

**Request handlers are thin.** `app.py` parses and validates input, calls into `engine/` or `services/`, and serializes the result. The actual heavy lifting happens within those packages. Check their respective README files and `app.py`'s endpoint inventory for details.

## 4. Algorithmic design

The core of the app is `engine/router.py`'s `_dijkstra_search`: a single-source shortest-path search over a graph of transit stops, BIXI docks, and user coordinates. The edges represent walking, biking, and transit rides scheduled against the real GTFS timetable. 

Three main design choices make it fast enough to run per-request:
- **Precompute static data:** Walking and cycling times between fixed points are resolved once offline against a real street router and cached in `walk_graph_cache.pkl`. A single search evaluates thousands of candidate edges. Live-resolving all of them would take minutes. We restrict live routing calls strictly to the user's specific click locations.
- **Self-hosted OSRM:** We use two local Docker containers instead of a paid routing API. This provides free, unlimited routing at 20-50ms latency, making the offline precompute step feasible at scale.
- **Preference scoring:** The search minimizes travel time plus a transfer penalty and a walk tie-break, rather than raw time alone. This prevents fragile routes that look fast on paper but demand perfect transfer timing. The user interface always displays the real, un-padded durations.

**Risk scoring** (`engine/risk.py`) is an additive model layered onto the final itinerary. It starts at 0 and adds penalties for risk factors like low BIXI availability or tight transfer buffers, normalized by leg count. We moved to this additive model because users found the previous subtractive model opaque. The point-based framing ensures users can easily trace why a route received a specific score.

**Tunable constants** are centralized in `engine/weights_config.py`. Walking speeds, access radii, and penalties are defined here alongside inline rationales. Centralizing these values means tuning behavior requires a single change with documented context, rather than hunting through `router.py`.

## 5. Frontend

The frontend is a single-page app with **no build step, no bundler, and no framework**. `templates/index.html` loads `static/js/map.js` and `static/css/style.css` directly via standard `<script>` and `<link>` tags. This matches the actual requirements: a single map view, a sidebar, no client-side routing, and a shallow component tree. Adding build tooling would introduce maintenance overhead without providing meaningful architectural benefits.

`map.js` is approximately 1400 lines and organized into feature areas marked by banner comments (search for `====`). Sections include map setup, address search, weather UI, next-departures, live-vehicle polling, and legend controls. Since none of these are reused or complex enough to justify module boundaries, they remain in a single file.

The frontend communicates with the backend exclusively through the JSON endpoints documented in `app.py`. There are no server-rendered partials beyond the initial HTML shell.

## 6. Data pipeline

The pipeline is split into two distinct categories:
- **Offline precompute:** Located in `data/scripts/`. This handles GTFS downloads, the walk/bike graph cache, and the elevation tile. These scripts run manually or via the admin refresh jobs, never during a user request.
- **Request-time services:** Located in `services/`. These handle BIXI availability, STM realtime, weather, and geocoding. All are live external calls wrapped to fail soft (returning `None`, `{}`, or `[]`) so an outage only degrades a specific feature instead of breaking the entire trip planner.

## 7. Testing / validation

There is no conventional unit-test suite. The routing algorithm's correctness is validated against real-world trips via the harness in `testing/`. This uses a fixed set of 38 canonical origin/destination pairs. Each is run through the live app and can optionally be compared against Google Routes API queries as an independent oracle. This harness catches regressions effectively by testing the actual itinerary quality before and after codebase changes.

## 8. Key decisions, and why

| Decision | Why |
|---|---|
| Self-hosted OSRM instead of a paid API | Provides free, unlimited local calls required to make the offline precompute pass practical. |
| Precompute static walk/bike distances | A single search touches thousands of edges. Resolving them live was measured to take 1-2 minutes per query. |
| Static GTFS schedule with a realtime overlay | The STM's realtime feed only covers buses. The static schedule is the only complete data source across all transit modes. Realtime data is used to adjust predictions, not replace the schedule. |
| Additive risk score | The original subtractive model wasn't legible. The additive model ensures every point is traceable to a specific, named risk factor. |
| In-memory caching, no database | The app is single-instance and schedule data changes only during explicit admin refreshes. A database's concurrency features aren't needed for read-only static data. |
| No frontend framework or bundler | A single view and a shallow component tree mean a framework's benefits do not offset the added build tooling. |
| Route-validation harness over unit tests | Routing correctness is about itinerary quality, which is best validated against real origin/destination pairs and an independent oracle rather than internal data structure assertions. |