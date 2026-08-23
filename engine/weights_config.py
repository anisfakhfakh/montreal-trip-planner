WALK_SPEED_MPS = 1.35  # ~4.9 km/h
BIKE_SPEED_MPS = 4.61  # 16.6 km/h, Montreal-specific published cycling-speed study
                        # (findingspress.org/article/11900), see PHASE3_FEEDBACK_PLAN.md item 3.
EBIKE_SPEED_MPS = 4.85  # ~17.4 km/h, BIKE_SPEED_MPS x ~1.05, the e-bike/classic ratio from the
                         # German Naturalistic Cycling Study (18.5 vs 17.6 km/h real-trip GPS
                         # speeds). Estimate, not Montreal-specific, no BIXI e-bike study exists.

# When the user unchecks "Walking (5+ minutes)" in the mode-selection UI: no single walk leg
# (access, transfer, or egress alike) may exceed this, a hard cap per leg, not a total-
# walking-time budget (e.g. five separate 3-minute transfer walks are still fine).
WALK_LEG_HARD_CAP_SEC = 300

# How far a rider is willing to walk to/from the actual click points on the map.
ORIGIN_DEST_ACCESS_RADIUS_M = 900
# How far a rider is willing to walk between two transit stops to transfer.
TRANSFER_WALK_RADIUS_M = 350
# How far a rider is willing to walk to reach a BIXI dock.
BIXI_ACCESS_RADIUS_M = 400
# How far a rider is willing to cycle between two BIXI stations.
BIXI_RIDE_RADIUS_M = 4000
# If the whole trip is shorter than this walking directly, don't bother routing through transit.
MAX_DIRECT_WALK_M = 1200

# How far outside the real station network (metro/REM stops + BIXI docks) the map/search is
# allowed to extend, covers the last-mile beyond the outermost stations without drifting into
# areas the app can't usefully route through.
MAP_BOUNDS_PADDING_M = 2000

# Hard cap on a single continuous BIXI ride, applied to every search (base result and all
# alternatives), past this, the search must dock and re-rent (or switch to transit) rather
# than stay on one bike for the whole stretch. Riders don't want 60+ minute uninterrupted
# rides even when one is nominally fastest on paper.
MAX_BASE_BIKE_LEG_SEC = 2700

# The "shorter BIXI legs" alternative's hard cap on a single continuous bike ride (see
# plan_trip_alternatives), stricter than MAX_BASE_BIKE_LEG_SEC above, forces the search to
# lean on transit for the bulk of the distance and BIXI for a short hop (typically last-mile)
# instead of one long uninterrupted ride, so a real Bus/Metro/REM + BIXI hybrid can surface as
# its own alternative when it's competitive.
MAX_HYBRID_BIKE_LEG_SEC = 600

# BIXI dock/bike availability marker thresholds (Section 6): green / orange / red.
BIXI_PLENTY_THRESHOLD = 5
BIXI_FEW_THRESHOLD = 1

# STM/REM GTFS route_type values (standard GTFS spec) used to pick line styling.
ROUTE_TYPE_METRO = 1
ROUTE_TYPE_BUS = 3
ROUTE_TYPE_REM = 0  # REM's own feed labels itself as tram/light rail (type 0)

# Extra time to walk from station entrance down to the metro/REM platform, applied on top
# of the scheduled departure when boarding these modes (buses board curbside, no penalty).
METRO_STATION_ENTRY_TIME_SEC = 90
# Symmetric penalty for walking back up from the platform to street level after alighting.
METRO_STATION_EXIT_TIME_SEC = 90

# Time to unlock a bike (~30s) and dock it again (~30s), charged once per BIXI edge traversed.
BIXI_DOCK_TIME_SEC = 60

# Discourages routes that board an extra vehicle just to shave a small amount of real time
# off the trip (e.g. hop one stop on a different bus, then walk to intercept the original bus
# further down its route before it passes), fragile in practice (miss the first connection
# or walk a bit slow and you've missed the whole thing), even when technically faster on
# paper. Added to Dijkstra's internal comparison cost only, once per boarding after the
# first, never applied to the very first boarding of a trip, and never shown in displayed
# times, which stay real/accurate. A route must save more real time than this per extra
# transfer to be worth taking. Confirmed with the user after a real-trip report of exactly
# this pathology (PHASE6_PLAN.md).
TRANSFER_PENALTY_SEC = 240

# Tiny extra weight on walking time in Dijkstra's cost (not in displayed times), purely a
# tie-breaker. Two paths that board the exact same real vehicle can end up with genuinely
# identical total cost (e.g. "walk further to a farther stop, wait less" vs "walk less, wait
# more" for the same bus). Ordinary Dijkstra has no basis to prefer either, so it can
# arbitrarily settle on the more-walking option. This nudges ties, and only ties since it's
# too small to ever outweigh a real time difference, toward less walking, since waiting is
# generally less effortful/risky than an equivalent stretch of walking. Confirmed via a real
# reported case where both options provably converged to the identical boarding time
# (PHASE6_PLAN.md).
WALK_TIEBREAK_WEIGHT = 1.001

# A stop can be served by several distinct routes/directions sharing one stop_id (e.g. a
# station where both directions of a line board from the same platform). Boarding search
# looks at the earliest departure per distinct (route, next stop) pattern within this window,
# rather than only the single soonest departure overall, otherwise a busy direction leaving
# sooner can permanently hide a different, useful direction/route that leaves a bit later.
PATTERN_LOOKAHEAD_SEC = 10800  # 3h: generous enough to still find sparse overnight service
# Scanning stops as soon as this many distinct patterns are found (not the 6 best, just the
# first 6 hit while scanning forward in time), so a busy multi-route stop with more than this
# many simultaneous routes/directions could silently never offer its 7th+ pattern to Dijkstra
# at all, observed as specific bus-to-bus combinations intermittently going missing depending
# on which stop the transfer happens at. Raised from 6 to cut that risk down; still bounded
# (not "scan everything") to keep the per-settle cost this project has stayed careful about.
MAX_PATTERNS_PER_STOP = 10

# Rough allowance for traffic lights/intersections/curb cuts that real OSRM distance/speed
# alone doesn't account for. Applied as a multiplier on top of distance / speed.
WALK_STOP_OVERHEAD_FACTOR = 1.10
BIKE_STOP_OVERHEAD_FACTOR = 1.15

# A walk leg this short (or shorter) is display noise (e.g. "0 min"), fold it into a
# neighboring leg instead of giving it its own itinerary bullet or counting toward the
# itinerary's mode label (e.g. don't call a trip "Bus + Walking" over a 20-second walk).
MIN_DISPLAYED_WALK_LEG_SEC = 60

# A gap before a scheduled (transit) departure shorter than this isn't worth a separate
# "wait" bullet in the itinerary, below this it's folded silently into the surrounding legs.
WAIT_LEG_MIN_SEC = 30

# A walk leg directly between two transit legs (no real access/egress walk on either side) whose
# straight-line (haversine) distance is at or under this cap is a same-station/short transfer
# ("correspondance"), not a real walk, GTFS stop coordinates for different platforms/directions
# at one physical station complex can be genuinely just a few meters apart, but a street-level
# walking-route engine with no indoor/underground network data can still compute a long, spurious
# detour between them (e.g. an "8 minute walk" between the Orange and Green line platforms at
# Berri-UQAM, which are actually a short in-station transfer). Deliberately checked against
# straight-line distance, not the routed distance/duration, since it's exactly the routed value
# that can be spuriously inflated. See engine/router.py's _mark_correspondance_walks.
CORRESPONDANCE_MAX_DISTANCE_M = 20

# Plain-language risk thresholds shown next to a "wait" leg (replaces the old numeric
# "reliability" score, which users found too opaque/inaccurate to act on): how much buffer is
# left before the scheduled bus/metro/REM departure.
WAIT_RISK_DANGER_SEC = 60   # <=1 min buffer: "high risk of missing it"
WAIT_RISK_WARN_SEC = 180    # <=3 min buffer: "moderate risk of missing it"

# Numeric risk-score model (engine/risk.py): starts at 0, adds a penalty point per risk
# factor, normalized by leg count. Replaces the old 100-start-subtract probability.py model.
# All penalty values tunable here; not yet mapped to a color/severity threshold (pending a
# calibration pass against real trips).
RISK_BIXI_FEW_PENALTY = 5
RISK_BIXI_NONE_PENALTY = 10

# Buffer before a transit leg's scheduled departure (gap between the previous leg's arrival
# and this leg's departure, same value used for the plain-language wait-risk labels above,
# but with its own thresholds/points for the numeric score).
RISK_TRANSIT_BUFFER_DANGER_SEC = 60    # <=1 min buffer
RISK_TRANSIT_BUFFER_WARN_SEC = 120     # <2 min buffer
RISK_TRANSIT_BUFFER_DANGER_PENALTY = 10
RISK_TRANSIT_BUFFER_WARN_PENALTY = 5

# "Cost of missing the next departure": only applied on top of a buffer penalty above.
# It's how long you'd be stuck if you missed this one, based on when the next departure of the
# same route from the same stop actually is (real GTFS schedule lookup, not a guess).
RISK_NEXT_DEPARTURE_UNDER_15MIN_PENALTY = 5
RISK_NEXT_DEPARTURE_UNDER_30MIN_PENALTY = 10
RISK_NEXT_DEPARTURE_UNDER_45MIN_PENALTY = 15
RISK_NEXT_DEPARTURE_OVER_45MIN_PENALTY = 20

# Map display colors that override the raw GTFS route_color for legs/station markers.
# Metro's real GTFS colors (green/orange/yellow/blue per line) are used as-is, no override
# needed there. Bus routes have real GTFS colors too, but the user wants a single consistent
# blue for all bus legs/markers rather than per-route colors. REM's real GTFS color (olive
# green, ~73A400) reads too close to metro Line 1's green, overridden to a color not used
# by any metro line, walking, or BIXI.
# Bus and metro Line 5 (Blue) were originally two very similar-looking blues (1565C0 vs the
# real GTFS 0095E6), the user asked to swap them so the two are visually distinct instead of
# both reading as "the blue one". METRO_BLUE_LINE_REAL_COLOR is Line 5's real GTFS route_color,
# used to detect it; METRO_BLUE_LINE_DISPLAY_COLOR is what it's shown as instead.
BUS_LINE_COLOR = "0095E6"
REM_LINE_COLOR = "8E44AD"
METRO_BLUE_LINE_REAL_COLOR = "0095E6"
METRO_BLUE_LINE_DISPLAY_COLOR = "1565C0"

# Fixed per-direction speed multipliers for bike-mode edges only (BIXI-to-BIXI), not walk edges.
# Deliberately not a continuous grade->speed function, classifies each stretch of a route as
# net-ascending/net-descending/flat (see engine/elevation.py + ascend_m/descend_m precomputed in
# data/scripts/precompute_walk_graph.py) and applies one multiplier per class, weighted by that
# class's own real distance, not netted against the whole route. Tunable estimates, not from a
# specific published coefficient (the directly relevant paper, Mohamed & Bigazzi 2019, is
# paywalled; only the qualitative direction, e-bikes far less affected by uphill grade, is
# confirmed). Revisit after a real-trip comparison.
CLASSIC_UPHILL_FACTOR = 0.75
CLASSIC_DOWNHILL_FACTOR = 1.20
EBIKE_UPHILL_FACTOR = 0.92
EBIKE_DOWNHILL_FACTOR = 1.10

# Montreal's open-data construction/closures and events datasets are point-based (one lat/lon
# per permit/event), not a polygon or line, so "does this route pass through active
# construction/an event" is a straight-line proximity check against sampled points along each
# leg's path, not real GIS intersection (the route geometry has no street names to match
# against). Informational only (see engine/router.py), neither feeds the risk score. Kept
# tight (well under a typical Montreal block width) specifically so a hit on a parallel or
# cross street doesn't get flagged as if it were on the traveled road.
CONSTRUCTION_PROXIMITY_RADIUS_M = 20
EVENT_PROXIMITY_RADIUS_M = 20

# Weather-discomfort trigger (engine/weather.py): a plain boolean "is right-now weather harsh
# enough to warn a walking/BIXI rider" flag with a short human-readable reason, deliberately
# not a numeric 1-3 discomfort score (considered too subjective/opaque, same reasoning that
# replaced the old probability.py score with plain-language risk labels). Cold side uses
# Environment Canada's own windchill comfort scale ("risk increases" band starts here); hot
# side uses their humidex scale ("great discomfort" band), computed from real temp + dewpoint
# already in the currentConditions payload, not arbitrary numbers.
WINDCHILL_DISCOMFORT_THRESHOLD_C = -20
HUMIDEX_DISCOMFORT_THRESHOLD = 40

# Substring keyword match (case-insensitive) against Environment Canada's current-condition
# text. Plain "rain" alone doesn't trigger, only once it's heavy; plain "snow"/"flurries" do,
# since even light snow meaningfully affects walking/cycling traction.
SEVERE_PRECIP_KEYWORDS = (
    "heavy rain", "snow", "flurries", "freezing rain", "freezing drizzle", "ice pellets", "blizzard",
)
