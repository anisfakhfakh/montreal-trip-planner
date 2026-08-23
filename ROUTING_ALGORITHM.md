# How the trip-planning algorithm actually works

This is a plain-language walkthrough of the routing engine, designed to be readable without knowing the codebase. Analogies are defined upfront and used consistently instead of variable names. A short appendix at the end maps each concept back to the real files and functions.

---

## 1. The core idea, in one picture

Imagine standing at your starting point holding a stopwatch. You send out ripples in every direction at once. One ripple goes down every street you could walk, one down every bus or train line you could board, and one to every bike-share dock you can reach. Each ripple travels at the real speed of that mode. 

The very first ripple to reach any given place tells you the fastest possible way to get there. Once a ripple reaches your destination, you know for certain that it represents the fastest trip. Every other ripple still traveling is, by definition, moving toward somewhere else it hasn't reached yet and can no longer beat the one that just arrived.

That is the entire algorithm: **expand outward from the start, always continuing from whichever reachable place currently has the earliest known arrival time, until you reach the destination.** This is a classical Dijkstra shortest-path search. The ripple analogy describes exactly how it behaves.

## 2. The vocabulary this document uses

| Plain term | What it means here |
|---|---|
| **Waypoint** | Any place the ripple can stand still: a bus/metro/REM stop, a bike-share dock, your exact start point, or your exact destination point. |
| **Connection** | A way to get from one waypoint to another by riding a specific bus/train, walking, or biking. Each connection has a real duration. |
| **The map** | All waypoints plus all possible connections between them. This map is never built all at once (see §4). |
| **Cheapest-known-arrival board** | A running scoreboard holding the earliest arrival time found so far, with one entry per waypoint. It updates every time a ripple reaches a waypoint faster than any previous ripple. |
| **Frontier** | The set of ripple-edges still "in flight." It is ordered so the algorithm always processes the earliest arrival time next. |
| **Breadcrumb** | Every time the scoreboard updates for a waypoint, it records which connection got us there. Following breadcrumbs backward from the destination reconstructs the entire trip. |
| **Settled** | A waypoint is "settled" once it has been processed and its scoreboard entry is finalized. It is never revisited. |

## 3. Two extra ideas that make transit routing work correctly

**A. "Still riding" is fundamentally different from "just arrived."** 
If you are already on a bus, continuing to the next stop is free. There is no new wait and no new boarding. If you just walked up to that same stop, you still owe a boarding wait. The algorithm tracks these as genuinely separate waypoint states. "At this stop, still aboard trip #123" is tracked separately from "at this stop, just arrived on foot." This ensures a fast walking ripple can never accidentally shadow a ripple that is already mid-ride and requires no wait time.

**B. The algorithm does not minimize raw clock time.** 
The routing engine optimizes a slightly adjusted "preference score." This includes real travel time, a small fixed penalty for every extra vehicle boarded beyond the first, and a tiny nudge against walking when two options are otherwise tied. This prevents the algorithm from proposing fragile routes that are technically 60 seconds faster on paper but require a perfectly timed sprint between vehicles. This adjustment only applies to internal comparisons; the displayed times are always the real, un-padded numbers.

## 4. Getting the data ready before a search

None of the following tasks happen while you wait for a search to load. They are completed ahead of time so the data can be looked up instantly.

- **Bus/metro/REM schedules:** The raw published schedule files are read once and reorganized. Every stop gets a single sorted list of everything departing from it and at what time. Finding the next bus after 3:15 PM becomes a fast array jump instead of scanning a timetable. The system also pre-filters which schedule applies today (weekday, weekend, or holiday), so that lookup is instant.
- **Walking and biking travel times:** Every stop and bike-share dock has a fixed real-world location. The walking or biking time between any two nearby points is computed offline using a real street routing engine. During an actual search, these numbers are read directly from a table.
- **Hills:** Uphill and downhill sections of each precomputed bike route are factored into the precomputed table. A live search never calculates elevation data because it is already baked into the travel time.
- **Click points:** The exact locations you click are the only points that cannot be precomputed. The moment you click "Plan trip," the system fires a quick burst of real routing calls specifically for your two coordinates to find nearby stops and docks. This happens before the ripple search begins.
- **Live data:** Dynamic information like current bike dock availability and live bus positions refreshes in the background on a short timer. It is read from the latest state rather than recomputed per search.

## 5. Step by step: what happens between clicking "Plan trip" and seeing a route

1. **Find your on-ramps:** Using the fresh routing calls from your exact click points, the system identifies which stops and bike-share docks are within walking distance of your start and end locations.
2. **Start the ripple:** The search begins at your starting point. The cheapest-known-arrival board holds one entry: "start point, time zero."
3. **Process the frontier:** The system processes one waypoint at a time, strictly prioritizing the earliest-arriving one. Every time a waypoint is processed, it looks at everything reachable directly from it:
   - If you arrived still riding a vehicle, continuing to the next scheduled stop is offered as a free connection.
   - Regardless of how you arrived, several of the soonest upcoming departures are offered as "board here" connections. We look at a handful of realistic options, not just the single next departure, so a useful route leaving a few minutes later isn't hidden by a busier one.
   - Walking to every other stop or bike dock within a short radius is offered.
   - If you are at a bike-share dock, biking to every other dock within range (that currently has an open spot) is offered.
   - Walking straight to your final destination is offered if it is close enough.
   For each option, if the resulting arrival time beats whatever was on the cheapest-known-arrival board, the board updates and a new breadcrumb is recorded.
4. **Repeat until the destination is processed:** Because the frontier always processes the earliest-arriving unsettled waypoint next, the destination's arrival time is guaranteed final the moment it is reached. Nothing in the frontier could possibly beat it. 
5. **Walk the breadcrumbs backward:** The system traces the breadcrumbs from the destination back to the start to reconstruct the trip as an ordered list of connections.
6. **Clean up for display:** The system formats the route for the UI. It merges consecutive rides on the same vehicle into a single leg. It relabels short walks between platforms in the same station as same-station transfers. It replaces straight-line transit connections with real street and track shapes. It inserts explicit "waiting" steps for scheduled gaps, and it flags risks like tight connections or low bike availability.
7. **Generate alternatives:** The entire process (steps 2 through 6) runs a few additional times with certain modes disabled entirely (e.g., "no bike-share allowed" or "no buses allowed"). This produces genuinely different route options rather than minor variations of the exact same path. If a re-run is mathematically guaranteed to produce the same answer because the winning route didn't use the disabled mode anyway, it is skipped to save time.

## 6. Why you can trust the result is actually the fastest option

Because the ripple always processes the cheapest unsettled waypoint next, and because no connection takes negative time, a waypoint is never settled too early. Anything that could still beat it is already slower than it right now. This mathematical guarantee ensures the destination's arrival time is final and correct the moment it is reached.

---

## Appendix: where this lives in the code

| Plain-language concept | Code location |
|---|---|
| The ripple search itself | `_dijkstra_search()` in [engine/router.py](engine/router.py#L476) |
| Waypoint = a stop / bike dock / origin / destination | node keys `("stop", stop_id, riding_trip_id)`, `("bixi", station_id)`, `ORIGIN`, `DEST` |
| "Still riding" vs "just arrived" | the `riding_trip_id` slot in the stop node key (see the docstring at [router.py:476](engine/router.py#L476)) |
| Cheapest-known-arrival board | the `dist` dict (real time) and `cost` dict (search-preference score) |
| Frontier | the `heap` (Python `heapq`) |
| Breadcrumbs | the `prev` dict |
| Settled set | the `settled` set |
| Preference-score adjustment | `TRANSFER_PENALTY_SEC`, `WALK_TIEBREAK_WEIGHT` in [engine/weights_config.py](engine/weights_config.py#L70) |
| Schedule preprocessing | `_build_trip_stops_and_departures()` in [engine/graph_builder.py](engine/graph_builder.py#L139) |
| Precomputed walk/bike travel times | `data/scripts/precompute_walk_graph.py` (offline) → `engine/walk_graph.py`'s `WalkGraph.lookup()` |
| Live click-point routing calls | `_resolve_dynamic_context()` in [router.py:448](engine/router.py#L448) |
| Cleanup pass | `_merge_legs`, `_mark_correspondance_walks`, `_attach_transit_shapes`, `_insert_wait_legs` (all in `router.py`), `compute_risk_score` (in [engine/risk.py](engine/risk.py#L86)) |
| Alternatives / mode-off re-runs | `plan_trip_alternatives()` in [router.py:906](engine/router.py#L906) |