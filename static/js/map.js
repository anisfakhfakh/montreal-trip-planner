// Map setup: Leaflet init, base layers, service-area bounds, shared constants
const MONTREAL_CENTER = [45.5019, -73.5674];
const ROUTE_TYPE_REM = 0;
const ROUTE_TYPE_METRO = 1;
const ROUTE_TYPE_BUS = 3;
// Bus and metro Line 5 (Blue) display colors are intentionally swapped from their "natural"
// values (bus's own GTFS blue vs. the real GTFS 0095E6 for Line 5) so the two don't both read
// as "the blue one", see engine/weights_config.py's METRO_BLUE_LINE_* constants, which is
// the backend half of this same swap.
const BUS_STOP_COLOR = "#0095E6";
const BIXI_MARK = { plenty: "", few: "!", empty: "!!" };
const BIXI_NEAR_RADIUS_M = 400;
// Metro line route_color (hex, matches the legend/GTFS routes.txt, post Blue-Line color swap
// above) -> the matching logo file.
const METRO_LOGO_BY_COLOR = {
  "00B300": "green_STM.png",
  "D95700": "orange_STM.png",
  "FFD900": "yellow_STM.png",
  "1565C0": "blue_STM.png",
};
const TRANSIT_LOGO_PX = 26;

const map = L.map("map").setView(MONTREAL_CENTER, 12);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  maxZoom: 19,
}).addTo(map);

// Stop the map from zooming/panning out past the real station network (metro/REM/BIXI) plus a
// small margin, the app can't usefully route anywhere further out anyway.
fetch("/api/map_bounds").then((r) => r.json()).then((b) => {
  const serviceAreaBounds = L.latLngBounds([b.south, b.west], [b.north, b.east]);
  map.setMaxBounds(serviceAreaBounds);
  map.setMinZoom(map.getBoundsZoom(serviceAreaBounds, false));
  map.options.maxBoundsViscosity = 1.0;
});

const bixiLayer = L.layerGroup().addTo(map);
const stationLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);
const constructionLayer = L.layerGroup().addTo(map);
const eventsLayer = L.layerGroup().addTo(map);
const CONSTRUCTION_COLOR = "#FF8F00";
const EVENT_COLOR = "#D81B60";
let originMarker = null;
let destMarker = null;
let origin = null;
let destination = null;
// Display text for the departure/arrival mini-timeline entries, a station name kept as-is,
// a compact formatted address (see formatShortAddress), or the raw-click coordinate fallback.
let originDisplayName = null;
let destinationDisplayName = null;

// Address formatting & origin/destination point selection
// Montreal road names in Nominatim's "road" field carry their direction as a trailing French
// word (e.g. "Rue Sainte-Catherine Ouest"), translate it to a single English letter and pull
// it out of the street name for the compact "123 Street W, H3B 5L1" itinerary label.
const STREET_DIRECTION_TRANSLATIONS = { Est: "E", Ouest: "W", Nord: "N", Sud: "S" };

function formatShortAddress(address, fallback) {
  if (!address || !address.road) return fallback;
  let road = address.road;
  let direction = "";
  for (const [fr, abbr] of Object.entries(STREET_DIRECTION_TRANSLATIONS)) {
    if (road.endsWith(` ${fr}`)) {
      direction = abbr;
      road = road.slice(0, -(fr.length + 1));
      break;
    }
  }
  const street = [address.house_number, road].filter(Boolean).join(" ");
  const streetWithDir = direction ? `${street} ${direction}` : street;
  if (!streetWithDir) return fallback;
  return address.postcode ? `${streetWithDir}, ${address.postcode}` : streetWithDir;
}

const planBtn = document.getElementById("plan-trip-btn");
const planHint = document.getElementById("plan-trip-hint");
const resetBtn = document.getElementById("reset-btn");
const useLocationBtn = document.getElementById("use-location");
const resultsDiv = document.getElementById("results");
const weatherDebriefDiv = document.getElementById("weather-debrief");
const allowEbikeCheckbox = document.getElementById("allow-ebike");
const ebikeOptionDiv = document.getElementById("ebike-option");
const bixiModeCheckbox = document.querySelector('.mode-check[data-mode="bixi"]');

// "Allow electric BIXI" only makes sense once BIXI itself is a mode in play.
function updateEbikeOptionVisibility() {
  const show = bixiModeCheckbox.checked;
  ebikeOptionDiv.hidden = !show;
  if (!show && allowEbikeCheckbox.checked) {
    allowEbikeCheckbox.checked = false;
    refreshBixiLayer();
  }
}
bixiModeCheckbox.addEventListener("change", updateEbikeOptionVisibility);
updateEbikeOptionVisibility();

function updatePlanButtonState() {
  const ready = origin && destination;
  planBtn.hidden = !ready;
  planHint.hidden = ready;
}

function setOrigin(lat, lon, label, displayName) {
  origin = { lat, lon };
  if (originMarker) map.removeLayer(originMarker);
  originMarker = L.marker([lat, lon], { title: "Departure" }).addTo(map);
  animateMarkerDrop(originMarker);
  originSearch.input.value = label || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  originDisplayName = displayName || label || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  originClearBtn.hidden = false;
  updatePlanButtonState();
  setBixiPoint("origin", lat, lon);
}

function setDestination(lat, lon, label, displayName) {
  destination = { lat, lon };
  if (destMarker) map.removeLayer(destMarker);
  destMarker = L.marker([lat, lon], { title: "Destination" }).addTo(map);
  animateMarkerDrop(destMarker);
  destSearch.input.value = label || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  destinationDisplayName = displayName || label || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  destClearBtn.hidden = false;
  updatePlanButtonState();
  setBixiPoint("destination", lat, lon);
}

function clearOrigin() {
  origin = null;
  originDisplayName = null;
  if (originMarker) map.removeLayer(originMarker);
  originMarker = null;
  originSearch.clear();
  originClearBtn.hidden = true;
  updatePlanButtonState();
  bixiPoints.delete("origin");
  refreshBixiLayer();
}

function clearDestination() {
  destination = null;
  destinationDisplayName = null;
  if (destMarker) map.removeLayer(destMarker);
  destMarker = null;
  destSearch.clear();
  destClearBtn.hidden = true;
  updatePlanButtonState();
  bixiPoints.delete("destination");
  refreshBixiLayer();
}

// `label` doubles as the display name here since every caller of handlePointSelection (map
// clicks, station/BIXI marker clicks) either has no name at all (raw click -> coordinate
// fallback) or a name that should be kept as-is (a station/dock name, not an address to format).
function handlePointSelection(lat, lon, label) {
  if (!origin) {
    setOrigin(lat, lon, label, label);
  } else if (!destination) {
    setDestination(lat, lon, label, label);
  }
}

// Map click / "use my location" / reset / address search inputs
map.on("click", (e) => handlePointSelection(e.latlng.lat, e.latlng.lng));

useLocationBtn.addEventListener("click", () => {
  if (!navigator.geolocation) {
    alert("Geolocation is not available in this browser.");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => setOrigin(pos.coords.latitude, pos.coords.longitude, "My location"),
    () => alert("Could not get your location.")
  );
});

resetBtn.addEventListener("click", () => {
  origin = null;
  destination = null;
  originDisplayName = null;
  destinationDisplayName = null;
  if (originMarker) map.removeLayer(originMarker);
  if (destMarker) map.removeLayer(destMarker);
  originMarker = null;
  destMarker = null;
  originSearch.clear();
  destSearch.clear();
  originClearBtn.hidden = true;
  destClearBtn.hidden = true;
  routeLayer.clearLayers();
  constructionLayer.clearLayers();
  eventsLayer.clearLayers();
  stopLiveVehiclePolling();
  vehicleMarkers.clear();
  resultsDiv.innerHTML = "";
  weatherDebriefDiv.innerHTML = "";
  currentWeather = { available: false, harsh: false, reason: null, condition: null };
  weatherAltReturnIdx = null;
  isPlannedTrip = false;
  setTripTiming("now");
  updatePlanButtonState();
  bixiPoints.delete("origin");
  bixiPoints.delete("destination");
  clearBixiPointsWithPrefix("trip-");
  refreshBixiLayer();
});

const SEARCH_DEBOUNCE_MS = 400;
const SEARCH_MIN_CHARS = 3;

// One shared shape for both the "From" and "To" boxes, each is independently searchable/
// editable (re-searching a filled field overwrites just that point), unlike map/marker clicks
// which go through handlePointSelection's "fill whichever is empty" behavior instead.
function makeSearchField(inputId, resultsId, onSelect) {
  const input = document.getElementById(inputId);
  const resultsList = document.getElementById(resultsId);
  let debounceTimer = null;
  let lastResults = [];

  async function runSearch(query) {
    const response = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    if (!response.ok) {
      lastResults = [];
      resultsList.innerHTML = `<li class="search-error">${data.error || "Search failed."}</li>`;
      return;
    }
    lastResults = data;
    resultsList.innerHTML = data.length
      ? data.map((r, i) => `<li data-idx="${i}">${r.name}</li>`).join("")
      : `<li class="search-error">No results found.</li>`;
  }

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const query = input.value.trim();
    if (query.length < SEARCH_MIN_CHARS) {
      lastResults = [];
      resultsList.innerHTML = "";
      return;
    }
    debounceTimer = setTimeout(() => runSearch(query), SEARCH_DEBOUNCE_MS);
  });

  resultsList.addEventListener("click", (e) => {
    const li = e.target.closest("li[data-idx]");
    if (!li) return;
    const result = lastResults[Number(li.dataset.idx)];
    if (!result) return;
    onSelect(result.lat, result.lon, result.name, formatShortAddress(result.address, result.name));
    resultsList.innerHTML = "";
  });

  return {
    input,
    resultsList,
    clear: () => { input.value = ""; resultsList.innerHTML = ""; lastResults = []; },
  };
}

const originSearch = makeSearchField("origin-search", "origin-search-results", setOrigin);
const destSearch = makeSearchField("dest-search", "dest-search-results", setDestination);
const originClearBtn = document.getElementById("origin-clear");
const destClearBtn = document.getElementById("dest-clear");
originClearBtn.addEventListener("click", clearOrigin);
destClearBtn.addEventListener("click", clearDestination);

// A quick scale/fade "drop" for a freshly placed origin/destination marker, Leaflet markers
// render as a plain <img>, so the animation is applied directly to that element after it's
// added to the map rather than through a custom divIcon.
function animateMarkerDrop(marker) {
  const el = marker.getElement ? marker.getElement() : marker._icon;
  if (el) el.classList.add("pin-drop");
}

// Itinerary leg rendering/formatting helpers (map polyline style + sidebar
// mini-timeline HTML), shared by renderItinerary() below
function formatClock(totalSeconds) {
  const secondsInDay = ((totalSeconds % 86400) + 86400) % 86400;
  const h = Math.floor(secondsInDay / 3600);
  const m = Math.floor((secondsInDay % 3600) / 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function legStyle(leg) {
  // "correspondance" is a short/same-station transfer walk (see engine/router.py's
  // _mark_correspondance_walks), not shown as its own itinerary bullet, but still drawn on the
  // map with the same style as a real walk leg.
  if (leg.mode === "walk" || leg.mode === "correspondance") return { color: "#555555", weight: 4, dashArray: "6,6" };
  if (leg.mode === "bike") return { color: "#D6001C", weight: 4 };
  if (leg.mode === "wait") return null;
  return { color: `#${leg.route_color}`, weight: 5 };
}

function transitLabel(leg) {
  return leg.transit_label || leg.route_short_name || "transit";
}

function riskWrap(leg, text) {
  if (leg.risk_level === "danger") return `<span class="risk-danger">${text} (${leg.risk_note})</span>`;
  if (leg.risk_level === "warn") return `<span class="risk-warn">${text} (${leg.risk_note})</span>`;
  return text;
}

// Same red already used for the map's bike-leg polyline (legStyle() below) and the legend's
// "Bike leg" swatch, reused here so the mini-timeline bar always matches the map.
const BIXI_BAR_COLOR = "#D6001C";
const EARTH_RADIUS_M = 6371000;

function haversineMeters(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

// No distance_m field ships on walk/bike legs (see engine/router.py), sum the real routed
// path instead, which is already sent for every leg.
function legDistanceMeters(leg) {
  let total = 0;
  for (let i = 1; i < leg.path.length; i++) {
    total += haversineMeters(leg.path[i - 1][0], leg.path[i - 1][1], leg.path[i][0], leg.path[i][1]);
  }
  return total;
}

function formatDistance(meters) {
  return meters > 1000 ? `${(meters / 1000).toFixed(1)} km` : `${Math.round(meters)} m`;
}

function waitModeLabel(routeType) {
  if (routeType === ROUTE_TYPE_BUS) return "Bus";
  if (routeType === ROUTE_TYPE_METRO) return "Metro";
  if (routeType === ROUTE_TYPE_REM) return "REM";
  return "transit";
}

// REM's own trip_headsign already carries its branch code (e.g. "A3 - Anse-à-l'Orme"), so
// prefixing route_short_name (e.g. "S3") would duplicate/garble it, show it alone.
function transitPrimaryText(leg) {
  if (leg.route_type === ROUTE_TYPE_REM) return leg.trip_headsign || "REM";
  return leg.trip_headsign ? `${leg.route_short_name} ${leg.trip_headsign}` : leg.route_short_name;
}

function legMinutes(leg) {
  return Math.round((leg.arr_sec - leg.dep_sec) / 60);
}

function pluralMinutes(mins) {
  return `${mins} minute${mins === 1 ? "" : "s"}`;
}

// Mode logo shown in the row's icon column, same artwork used for the map's own transit
// markers (metro/bus/REM) plus the user-supplied Walking/BIXI/Waiting logos for the other modes.
function transitLegLogoFile(leg) {
  if (leg.route_type === ROUTE_TYPE_BUS) return "bus.png";
  if (leg.route_type === ROUTE_TYPE_REM) return "REM.png";
  return METRO_LOGO_BY_COLOR[leg.route_color] || "blue_STM.png";
}

// `busBadge` clips bus.png's solid rounded-square artwork to a circle, matching the map's own
// bus marker treatment (transitLegIcon's .bus-logo-badge), metro/REM/Walking/BIXI/Waiting
// logos are already transparent-cornered and don't need it.
function legIconHtml(file, busBadge) {
  return `<div class="leg-icon${busBadge ? " leg-icon-bus-badge" : ""}"><img src="/static/img/${file}" alt=""></div>`;
}

// One mini-timeline row: a mode logo, a colored/dashed bar (matching the map's own leg colors),
// and a two-line text block, optionally followed by a construction/risk alert line, passed in
// as `extraHtml` (rather than appended outside the row by the caller) so the bar, which
// stretches to match its row's height, visually extends down to cover the alert too.
// `pairedWaitLeg` is set when a walk leg is immediately followed by a wait leg in the itinerary.
// Google Maps merges that pair into a single combined row ("Walk 320 m (4 minutes), then
// wait 6 minutes for Bus") instead of two separate rows.
function legTimelineHtml(leg, pairedWaitLeg, extraHtml) {
  const extra = extraHtml || "";
  if (leg.mode === "transit") {
    const stops = leg.num_stops || 1;
    return `<div class="leg-row">
      ${legIconHtml(transitLegLogoFile(leg), leg.route_type === ROUTE_TYPE_BUS)}
      <div class="leg-bar leg-bar-transit" style="background:#${leg.route_color}"></div>
      <div class="leg-text">
        <div class="leg-text-primary">${transitPrimaryText(leg)}</div>
        <div class="leg-text-secondary">${stops} station${stops === 1 ? "" : "s"} (${pluralMinutes(legMinutes(leg))})</div>
        ${extra}
      </div>
    </div>`;
  }
  if (leg.mode === "bike") {
    const label = leg.bike_type === "electric" ? "Electric BIXI" : "BIXI";
    const distanceText = `${formatDistance(legDistanceMeters(leg))} (${pluralMinutes(legMinutes(leg))})`;
    return `<div class="leg-row">
      ${legIconHtml("BIXI.png")}
      <div class="leg-bar leg-bar-bike" style="background:${BIXI_BAR_COLOR}"></div>
      <div class="leg-text">
        <div class="leg-text-primary">${riskWrap(leg, label)}</div>
        <div class="leg-text-secondary">${distanceText}</div>
        ${extra}
      </div>
    </div>`;
  }
  if (leg.mode === "walk" && leg.station_exit) {
    return `<div class="leg-row">
      ${legIconHtml("Walking.png")}
      <div class="leg-bar leg-bar-walk"></div>
      <div class="leg-text">
        <div class="leg-text-primary">Exit station</div>
        <div class="leg-text-secondary">${pluralMinutes(legMinutes(leg))}</div>
        ${extra}
      </div>
    </div>`;
  }
  if (leg.mode === "walk") {
    const baseText = `${formatDistance(legDistanceMeters(leg))} (${pluralMinutes(legMinutes(leg))})`;
    const secondary = pairedWaitLeg
      ? `${baseText}, then ${riskWrap(pairedWaitLeg, `wait ${pluralMinutes(legMinutes(pairedWaitLeg))} for ${waitModeLabel(pairedWaitLeg.route_type)}`)}`
      : baseText;
    return `<div class="leg-row">
      ${legIconHtml("Walking.png")}
      <div class="leg-bar leg-bar-walk"></div>
      <div class="leg-text">
        <div class="leg-text-primary">Walk</div>
        <div class="leg-text-secondary">${secondary}</div>
        ${extra}
      </div>
    </div>`;
  }
  // Standalone "wait" leg, no walk immediately preceded it (a same-stop or short in-station
  // transfer, i.e. a "correspondance", see engine/router.py's _mark_correspondance_walks,
  // which folds any short connecting walk's time into this leg's own span).
  return `<div class="leg-row">
    ${legIconHtml("correspondance.png")}
    <div class="leg-bar leg-bar-wait"></div>
    <div class="leg-text">
      <div class="leg-text-primary">${riskWrap(leg, `Transfer, wait ${pluralMinutes(legMinutes(leg))} for ${waitModeLabel(leg.route_type)}`)}</div>
      ${extra}
    </div>
  </div>`;
}

// Same blue pin artwork as the map's own origin/destination markers, `isEndpoint` is only
// true for the trip's actual departure/arrival entries (not the intermediate station dividers).
const MAP_PIN_ICON_URL = "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png";

// The icon column matches .leg-icon's own width so the pin lines up with the mode logos above/
// below it, keeping one continuous left-aligned column instead of a pin that floats wherever the
// (previously centered) text happened to start.
function legDividerHtml(name, sec, isEndpoint) {
  const pin = isEndpoint ? `<img class="leg-divider-pin" src="${MAP_PIN_ICON_URL}" alt="">` : "";
  return `<li class="leg-divider">
    <div class="leg-divider-icon">${pin}</div>
    <div class="leg-divider-text">${name} <span class="leg-divider-time">${formatClock(sec)}</span></div>
  </li>`;
}

function legDescription(leg) {
  const time = `${formatClock(leg.dep_sec)} - ${formatClock(leg.arr_sec)}`;
  let desc;
  if (leg.mode === "walk" && leg.station_exit) desc = `${time}: Exit ${leg.from_name} to street level`;
  else if (leg.mode === "walk") desc = `${time}: Walk from ${leg.from_name} to ${leg.to_name}`;
  else if (leg.mode === "correspondance") desc = `${time}: Transfer from ${leg.from_name} to ${leg.to_name}`;
  else if (leg.mode === "bike") {
    const label = leg.bike_type === "electric" ? "Electric BIXI" : "BIXI";
    desc = riskWrap(leg, `${time}: ${label} from ${leg.from_name} to ${leg.to_name}`);
  } else if (leg.mode === "wait") desc = riskWrap(leg, `${time}: Wait for ${transitLabel(leg)} at ${leg.to_name}`);
  else desc = `${time}: ${transitLabel(leg)} from ${leg.from_name} to ${leg.to_name}`;

  if (leg.construction_note) desc += ` <span class="risk-warn">⚠ ${leg.construction_note}</span>`;
  return desc;
}

function legItemHtml(leg, i, pairedWaitLeg) {
  const showRerouteBtn = leg.mode === "bike" && leg.construction_note;
  const button = showRerouteBtn
    ? `<button class="reroute-btn" data-leg-idx="${i}">Find an alternative path</button>`
    : "";
  const constructionNote = leg.construction_note
    ? `<div class="leg-text-secondary risk-warn">⚠ ${leg.construction_note}</div>`
    : "";
  return `<li data-leg-idx="${i}">${legTimelineHtml(leg, pairedWaitLeg, constructionNote)}${button}</li>`;
}

// Interleaves station/dock-name dividers before every transit or BIXI boarding (each transit leg
// in the final array is, by construction, a fresh boarding, see engine/router.py's
// _merge_legs) and before a walk leg that immediately follows one (the alighting stop, shown
// again right as you start walking away from it), collapses a walk immediately followed by a
// wait into one combined row (see legTimelineHtml), and brackets the whole list with dedicated
// departure/arrival entries for the trip's actual origin/destination (a station name kept as-is,
// or a compact formatted address, see formatShortAddress) instead of relying on the first/last
// leg's own from_name/to_name, which are backend placeholders ("Origin"/"Destination") whenever
// that leg touches the origin/destination point directly.
function buildLegItems(legs, data) {
  const items = [];
  items.push(legDividerHtml(originDisplayName || "Departure", data.departure_sec, true));
  let i = 0;
  while (i < legs.length) {
    const leg = legs[i];
    // "correspondance" legs never get their own row or divider, see engine/router.py's
    // _mark_correspondance_walks/_insert_wait_legs, their timespan is already folded into the
    // following standalone "wait" leg's display. They still exist in `legs` purely so the map
    // (renderItinerary) can draw their path.
    if (leg.mode === "correspondance") {
      i += 1;
      continue;
    }
    const prevLeg = i > 0 ? legs[i - 1] : null;
    const needsDivider = i > 0 && (
      leg.mode === "transit" || leg.mode === "bike"
      || (leg.mode === "walk" && prevLeg && (prevLeg.mode === "transit" || prevLeg.mode === "bike"))
    );
    if (needsDivider) items.push(legDividerHtml(leg.from_name, leg.dep_sec));
    const nextLeg = legs[i + 1];
    if (leg.mode === "walk" && nextLeg && nextLeg.mode === "wait") {
      items.push(legItemHtml(leg, i, nextLeg));
      i += 2;
    } else {
      items.push(legItemHtml(leg, i));
      i += 1;
    }
  }
  items.push(legDividerHtml(destinationDisplayName || "Arrival", data.arrival_sec, true));
  return items.join("");
}

// Itinerary state, sorting, and the main render function
let currentItineraries = [];
let selectedIndex = 0;
let sortState = { by: "duration", dir: "asc" };
let currentWeather = { available: false, harsh: false, reason: null, condition: null };
// Set when the currently-shown itinerary was reached via the weather-alt-route button, so the
// same button slot can flip to "go back" instead of only ever offering to switch away.
let weatherAltReturnIdx = null;
// True when the last search used "Leave at" a future time rather than "Leave now", BIXI
// availability can't be predicted that far ahead, so any BIXI leg in the results still reflects
// live-right-now station data (see bixiPlannedNoteHtml).
let isPlannedTrip = false;

// Below this much total walking, a leg isn't considered "exposed" to weather, matches the
// 5-minute threshold the user specified for the weather-friendly-route prompt.
const WEATHER_EXPOSURE_WALK_SEC = 300;

function itineraryWalkSec(itin) {
  return itin.legs.filter((leg) => leg.mode === "walk").reduce((sum, leg) => sum + (leg.arr_sec - leg.dep_sec), 0);
}

function itineraryHasBikeLeg(itin) {
  return itin.legs.some((leg) => leg.mode === "bike");
}

function itineraryWeatherExposed(itin) {
  return itineraryHasBikeLeg(itin) || itineraryWalkSec(itin) > WEATHER_EXPOSURE_WALK_SEC;
}

// Among the already-computed itineraries (no new search), the least-walking option with no
// BIXI leg at all, the concrete "weather-friendly" alternative to offer.
function findWeatherFriendlyAlternative(excludeIdx) {
  let best = null;
  currentItineraries.forEach((itin, i) => {
    if (i === excludeIdx || !itin.available || itineraryHasBikeLeg(itin)) return;
    const walkSec = itineraryWalkSec(itin);
    if (best === null || walkSec < best.walkSec) best = { idx: i, walkSec };
  });
  return best ? best.idx : null;
}

function transportLegCount(itin) {
  return itin.legs.filter((leg) => leg.mode === "transit" || leg.mode === "bike").length;
}

function sortValue(itin, by) {
  if (by === "legs") return transportLegCount(itin);
  if (by === "risk") return itin.risk_score;
  if (by === "construction") return itin.construction_events_count ?? Infinity;
  return itin.duration_sec;
}

// Available itineraries are sorted by the active column; unavailable ones (no real
// duration/legs/risk to compare) always sink to the bottom regardless of sort.
function sortedIndices() {
  const idxs = currentItineraries.map((_, i) => i);
  const available = idxs.filter((i) => currentItineraries[i].available);
  const unavailable = idxs.filter((i) => !currentItineraries[i].available);
  available.sort((a, b) => {
    // "-" (no bike leg, so no construction/events count at all) isn't a real value to rank, so
    // it always sinks to the bottom in either sort direction, same as unavailable itineraries.
    if (sortState.by === "construction") {
      const aCount = currentItineraries[a].construction_events_count;
      const bCount = currentItineraries[b].construction_events_count;
      if (aCount == null && bCount == null) return 0;
      if (aCount == null) return 1;
      if (bCount == null) return -1;
    }
    const diff = sortValue(currentItineraries[a], sortState.by) - sortValue(currentItineraries[b], sortState.by);
    return sortState.dir === "asc" ? diff : -diff;
  });
  return [...available, ...unavailable];
}

function sortArrow(field) {
  if (sortState.by !== field) return "";
  return sortState.dir === "asc" ? " ↑" : " ↓";
}

function itineraryHeaderHtml() {
  return `<div class="itinerary-header">
    <span class="option-label">Route</span>
    <span class="option-duration header-cell" data-sort-by="duration">Duration${sortArrow("duration")}</span>
    <span class="option-legs header-cell" data-sort-by="legs">Legs${sortArrow("legs")}</span>
    <span class="option-risk header-cell" data-sort-by="risk">Risk${sortArrow("risk")}</span>
    <span class="option-construction header-cell" data-sort-by="construction">Constr./Events${sortArrow("construction")}</span>
  </div>`;
}

function itineraryOptionHtml(itin, idx) {
  if (!itin.available) {
    return `<li class="itinerary-option unavailable">
      <span class="option-label">${itin.mode_label}</span>
      <span class="option-message">${itin.message}</span>
    </li>`;
  }
  const durationMin = Math.round(itin.duration_sec / 60);
  const legCount = transportLegCount(itin);
  const selected = idx === selectedIndex ? " selected" : "";
  const constructionText = itin.construction_events_count === null || itin.construction_events_count === undefined
    ? "-"
    : itin.construction_events_count;
  return `<li data-idx="${idx}" class="itinerary-option${selected}">
    <span class="option-label">${itin.mode_label}</span>
    <span class="option-duration">${durationMin} min</span>
    <span class="option-legs">${legCount} leg${legCount === 1 ? "" : "s"}</span>
    <span class="option-risk">${itin.risk_score.toFixed(1)}</span>
    <span class="option-construction">${constructionText}</span>
  </li>`;
}

function renderItinerary(idx) {
  selectedIndex = idx;
  const data = currentItineraries[idx];
  hideFloatingDepartures();

  const bounds = [];
  routeLayer.clearLayers();
  clearBixiPointsWithPrefix("trip-");
  vehicleMarkers.clear();
  data.legs.forEach((leg, i) => {
    const style = legStyle(leg);
    if (style) {
      const line = L.polyline(leg.path, style).addTo(routeLayer);
      line.bindPopup(legDescription(leg));
      if (leg.mode === "transit") {
        line.on("contextmenu", (e) => {
          L.DomEvent.preventDefault(e);
          showNextDepartures(leg, e.latlng);
        });
      }
    }
    if (leg.mode === "transit") {
      const marker = L.marker(pathMidpoint(leg.path), { icon: transitLegIcon(leg) })
        .bindTooltip(transitLabel(leg), { direction: "top" })
        .addTo(routeLayer);
      marker._staticLabel = transitLabel(leg);
      if (leg.trip_id) vehicleMarkers.set(leg.trip_id, marker);
    }
    if (leg.mode === "transit" && leg.route_type === ROUTE_TYPE_BUS) {
      [[leg.from, leg.from_name], [leg.to, leg.to_name]].forEach(([point, name]) => {
        L.circleMarker(point, {
          radius: 5, color: BUS_STOP_COLOR, fillColor: BUS_STOP_COLOR, fillOpacity: 0.9, weight: 1,
        })
          .bindTooltip(name, { direction: "top" })
          .addTo(routeLayer);
      });
    }
    if (leg.mode === "bike") {
      bixiPoints.set(`trip-${i}-from`, { lat: leg.from[0], lon: leg.from[1] });
      bixiPoints.set(`trip-${i}-to`, { lat: leg.to[0], lon: leg.to[1] });
    }
    leg.path.forEach((p) => bounds.push(p));
  });
  refreshBixiLayer();
  updateHazardMarkers(data);
  startLiveVehiclePolling();
  if (bounds.length) map.flyToBounds(bounds, { padding: [40, 40], duration: 0.9 });

  const durationMin = Math.round(data.duration_sec / 60);
  const legItems = buildLegItems(data.legs, data);
  const optionsHtml = sortedIndices().map((i) => itineraryOptionHtml(currentItineraries[i], i)).join("");
  resultsDiv.innerHTML = `
    <div class="itinerary-table">
      ${itineraryHeaderHtml()}
      <ul class="itinerary-options">${optionsHtml}</ul>
    </div>
    <h2>${data.mode_label} &mdash; ${durationMin} min</h2>
    <ul class="legs">${legItems}</ul>
    ${bixiPlannedNoteHtml(data)}
    ${weatherNoteHtml(idx)}
  `;
}

// Weather debrief/warning UI (harsh-weather note + "weather-friendly alternative" prompt)
// BIXI dock/bike counts can't be forecast for a future "Leave at" time, the backend just uses
// whatever's live right now (see PROJECT_PLAN.md/app.py's plan_trip, no BIXI-demand model
// exists). Flag that plainly under any route that actually has a BIXI leg.
function bixiPlannedNoteHtml(itin) {
  if (!isPlannedTrip || !itineraryHasBikeLeg(itin)) return "";
  return `<div class="bixi-planned-note">
    P.S. This route includes BIXI, the availability shown reflects live station data right
    now, not a forecast for your selected departure time.
  </div>`;
}

function weatherDebriefHtml() {
  if (!currentWeather.available) return "";
  const icon = currentWeather.harsh ? "⚠️" : "☀️";
  const tempText = currentWeather.temp_c !== null && currentWeather.temp_c !== undefined
    ? `${Math.round(currentWeather.temp_c)}°C, `
    : "";
  const harshClass = currentWeather.harsh ? " harsh" : "";
  const text = currentWeather.harsh
    ? `${tempText}${currentWeather.condition || currentWeather.reason}, ${currentWeather.reason}.`
    : `${tempText}${currentWeather.condition || "current conditions"}.`;
  return `<div class="weather-debrief${harshClass}"><span class="weather-icon">${icon}</span><span>${text}</span></div>`;
}

function weatherNoteHtml(idx) {
  if (weatherAltReturnIdx !== null && idx !== weatherAltReturnIdx) {
    return `<div class="weather-note">
      <p>Showing a weather-friendlier alternative.</p>
      <button class="weather-alt-btn" data-alt-idx="${weatherAltReturnIdx}" data-revert="true">Back to original route</button>
    </div>`;
  }

  const itin = currentItineraries[idx];
  if (!currentWeather.harsh || !itin.available || !itineraryWeatherExposed(itin)) return "";

  const altIdx = findWeatherFriendlyAlternative(idx);
  const altHtml = altIdx !== null
    ? `<button class="weather-alt-btn" data-alt-idx="${altIdx}">Consider another weather-friendly route?</button>`
    : `<p class="weather-note-empty">No weather-friendlier option among the computed routes.</p>`;
  return `<div class="weather-note">
    <p>This route has significant weather exposure.</p>
    ${altHtml}
  </div>`;
}

// Next-departures popups/panels + single-leg BIXI reroute-around-construction
async function showNextDepartures(leg, latlng) {
  const popup = L.popup({ closeButton: true })
    .setLatLng(latlng)
    .setContent(`<strong>${transitLabel(leg)}</strong><br>Loading next departures…`)
    .openOn(map);

  try {
    const response = await fetch("/api/next_departures", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: leg.route_id, from_stop: leg.from_stop, to_stop: leg.to_stop, departure_time: plannedDepartureIso() }),
    });
    const data = await response.json();
    const departures = response.ok ? data.departures || [] : [];
    const listHtml = departures.length
      ? `<ul class="next-departures-list">${departures.map((d) =>
          `<li>${formatClock(d.dep_sec)}${d.live ? ` <span class="live-badge" title="Live, delay-adjusted">live</span>` : ""}</li>`
        ).join("")}</ul>`
      : `<p class="next-departures-empty">No more scheduled departures found.</p>`;
    popup.setContent(`<strong>${transitLabel(leg)}</strong><br>Next departures from ${leg.from_name}:${listHtml}`);
  } catch (err) {
    popup.setContent(`<strong>${transitLabel(leg)}</strong><br>Could not load departure times.`);
  }
}

// Hovering a transit leg in the sidebar shows a small floating panel with its next departures,
// instead of the map's right-click popup (showNextDepartures above), same backend call,
// different context (a glance without clicking anything). Appended to <body> (not resultsDiv,
// which gets fully rebuilt on every render) and positioned via the hovered row's own
// bounding rect so it floats next to the row regardless of sidebar scroll position.
const floatingDeparturesEl = document.createElement("div");
floatingDeparturesEl.className = "floating-departures";
floatingDeparturesEl.hidden = true;
document.body.appendChild(floatingDeparturesEl);

// Bumped on every new hover so a slow-to-resolve fetch from a leg the cursor already left can't
// clobber the panel's content after a newer hover has taken over (or after it's been hidden).
let floatingDeparturesReqId = 0;

function hideFloatingDepartures() {
  floatingDeparturesEl.hidden = true;
  floatingDeparturesReqId += 1;
}

async function showFloatingDepartures(leg, anchorEl) {
  const reqId = ++floatingDeparturesReqId;
  const rect = anchorEl.getBoundingClientRect();
  floatingDeparturesEl.hidden = false;
  floatingDeparturesEl.style.left = `${rect.right + 8}px`;
  floatingDeparturesEl.style.top = `${Math.min(rect.top, window.innerHeight - 220)}px`;
  floatingDeparturesEl.innerHTML = `<strong>${transitLabel(leg)}</strong><p class="next-departures-loading">Loading&hellip;</p>`;

  try {
    const response = await fetch("/api/next_departures", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: leg.route_id, from_stop: leg.from_stop, to_stop: leg.to_stop, departure_time: plannedDepartureIso() }),
    });
    const data = await response.json();
    if (reqId !== floatingDeparturesReqId) return;
    const departures = response.ok ? data.departures || [] : [];
    const listHtml = departures.length
      ? `<ul class="next-departures-list">${departures.map((d) =>
          `<li>${formatClock(d.dep_sec)}${d.live ? ` <span class="live-badge" title="Live, delay-adjusted">live</span>` : ""}</li>`
        ).join("")}</ul>`
      : `<p class="next-departures-empty">No more scheduled departures found.</p>`;
    floatingDeparturesEl.innerHTML = `<strong>${transitLabel(leg)}</strong><p class="floating-departures-caption">Next departures from ${leg.from_name}:</p>${listHtml}`;
  } catch (err) {
    if (reqId !== floatingDeparturesReqId) return;
    floatingDeparturesEl.innerHTML = `<strong>${transitLabel(leg)}</strong><p>Could not load departure times.</p>`;
  }
}

async function handleReroute(legIndex, button) {
  button.disabled = true;
  button.textContent = "Finding detour…";
  try {
    const response = await fetch("/api/reroute_leg", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itinerary: currentItineraries[selectedIndex], leg_index: legIndex }),
    });
    const data = await response.json();
    if (!response.ok) {
      button.disabled = false;
      button.textContent = data.error || "No alternative route found.";
      return;
    }
    currentItineraries[selectedIndex] = data.itinerary;
    renderItinerary(selectedIndex);
  } catch (err) {
    button.disabled = false;
    button.textContent = "No alternative route found.";
  }
}

// Delegated event listeners for the results panel (sort headers, reroute
// button, weather-alt button, leg click-to-zoom, leg hover-for-departures)
resultsDiv.addEventListener("click", (e) => {
  const header = e.target.closest(".header-cell[data-sort-by]");
  if (header) {
    const by = header.dataset.sortBy;
    sortState = sortState.by === by ? { by, dir: sortState.dir === "asc" ? "desc" : "asc" } : { by, dir: "asc" };
    renderItinerary(selectedIndex);
    return;
  }
  const rerouteBtn = e.target.closest(".reroute-btn[data-leg-idx]");
  if (rerouteBtn) {
    handleReroute(Number(rerouteBtn.dataset.legIdx), rerouteBtn);
    return;
  }
  const weatherAltBtn = e.target.closest(".weather-alt-btn[data-alt-idx]");
  if (weatherAltBtn) {
    const targetIdx = Number(weatherAltBtn.dataset.altIdx);
    weatherAltReturnIdx = weatherAltBtn.dataset.revert === "true" ? null : selectedIndex;
    renderItinerary(targetIdx);
    return;
  }
  const legLi = e.target.closest(".legs li[data-leg-idx]");
  if (legLi) {
    const leg = currentItineraries[selectedIndex].legs[Number(legLi.dataset.legIdx)];
    if (leg.path && leg.path.length) {
      map.flyToBounds(L.latLngBounds(leg.path), { padding: [60, 60], duration: 0.7 });
    }
    return;
  }
  const li = e.target.closest(".itinerary-options li[data-idx]");
  if (!li) return;
  weatherAltReturnIdx = null;
  renderItinerary(Number(li.dataset.idx));
});

// mouseover/mouseout (not mouseenter/mouseleave, which don't bubble) so one delegated listener
// works across every re-render of #results instead of needing to be re-attached per row.
resultsDiv.addEventListener("mouseover", (e) => {
  const legLi = e.target.closest(".legs li[data-leg-idx]");
  if (!legLi || legLi.contains(e.relatedTarget)) return;
  const leg = currentItineraries[selectedIndex].legs[Number(legLi.dataset.legIdx)];
  if (leg.mode !== "transit") return; // only transit legs have route_id/from_stop/to_stop
  showFloatingDepartures(leg, legLi);
});

resultsDiv.addEventListener("mouseout", (e) => {
  const legLi = e.target.closest(".legs li[data-leg-idx]");
  if (!legLi || legLi.contains(e.relatedTarget)) return;
  hideFloatingDepartures();
});

// Mode-selection reading + "Leave now" vs "Leave at" trip-timing controls
function selectedModes() {
  const modes = {};
  document.querySelectorAll(".mode-check").forEach((el) => {
    modes[el.dataset.mode] = el.checked;
  });
  const maxWalk = document.getElementById("max-walk-minutes").value;
  modes.max_walk_minutes = maxWalk === "" ? null : Number(maxWalk);
  return modes;
}

// "Leave now" (default) vs "Leave at" a specific future time within the next week, BIXI
// availability can't be predicted that far out, so a planned trip still uses live BIXI data as
// of right now (see bixiPlannedNoteHtml below, shown under any route with a BIXI leg once a
// future time is chosen).
const LEAVE_AT_DAYS_AHEAD = 7;
const leaveNowBtn = document.getElementById("leave-now-btn");
const leaveAtBtn = document.getElementById("leave-at-btn");
const leaveAtFields = document.getElementById("leave-at-fields");
const leaveAtDateSelect = document.getElementById("leave-at-date");
const leaveAtTimeInput = document.getElementById("leave-at-time");
let tripTiming = "now"; // "now" | "at"

function pad2(n) {
  return String(n).padStart(2, "0");
}

function dateOptionValue(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function dateOptionLabel(d, isToday) {
  const formatted = d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  return isToday ? `Today, ${formatted}` : formatted;
}

// Rolling window: today through exactly one week from today (8 selectable days), per the
// user's "next 7 days until the same present time" spec.
function populateLeaveAtDates() {
  const today = new Date();
  leaveAtDateSelect.innerHTML = "";
  for (let i = 0; i <= LEAVE_AT_DAYS_AHEAD; i++) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() + i);
    const opt = document.createElement("option");
    opt.value = dateOptionValue(d);
    opt.textContent = dateOptionLabel(d, i === 0);
    leaveAtDateSelect.appendChild(opt);
  }
}

// Can't pick a time in the past for today's date, no restriction on future days.
function updateLeaveAtTimeMin() {
  const now = new Date();
  leaveAtTimeInput.min = leaveAtDateSelect.value === dateOptionValue(now) ? `${pad2(now.getHours())}:${pad2(now.getMinutes())}` : "";
}

function setTripTiming(timing) {
  tripTiming = timing;
  leaveNowBtn.classList.toggle("active", timing === "now");
  leaveAtBtn.classList.toggle("active", timing === "at");
  leaveAtFields.hidden = timing !== "at";
}

leaveNowBtn.addEventListener("click", () => setTripTiming("now"));
leaveAtBtn.addEventListener("click", () => setTripTiming("at"));
leaveAtDateSelect.addEventListener("change", updateLeaveAtTimeMin);

populateLeaveAtDates();
const nowForDefaultTime = new Date();
leaveAtTimeInput.value = `${pad2(nowForDefaultTime.getHours())}:${pad2(nowForDefaultTime.getMinutes())}`;
updateLeaveAtTimeMin();
setTripTiming("now");

// null when "Leave now" is active, api_plan_trip already defaults to datetime.now() itself.
function plannedDepartureIso() {
  if (tripTiming !== "at" || !leaveAtDateSelect.value || !leaveAtTimeInput.value) return null;
  return `${leaveAtDateSelect.value}T${leaveAtTimeInput.value}:00`;
}

// Toast notifications, loading skeleton, and the admin data-refresh card
const toastContainer = document.getElementById("toast-container");

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = `toast${isError ? " toast-error" : ""}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("visible"));
  setTimeout(() => {
    toast.classList.remove("visible");
    toast.addEventListener("transitionend", () => toast.remove(), { once: true });
  }, 4000);
}

// A trip search can take several (up to ~20) seconds, these pulsing placeholder rows fill the
// itinerary-option-shaped dead air until the real results replace them.
function skeletonHtml() {
  return `<div class="skeleton-block"><div class="skeleton-item"></div><div class="skeleton-item"></div><div class="skeleton-item"></div></div>`;
}

// Admin/maintenance card: manually trigger a cache rebuild (BIXI walk-graph precompute or STM
// GTFS re-download+rebuild) instead of running the underlying script by hand. Jobs run as a
// real backend subprocess (see engine/data_refresh.py) and can take 10-15+ minutes, so this is
// fire-and-poll, not a blocking request.
const REFRESH_JOBS = ["bixi", "stm"];
const refreshButtons = { bixi: document.getElementById("refresh-bixi-btn"), stm: document.getElementById("refresh-stm-btn") };
const refreshStatusEls = { bixi: document.getElementById("refresh-bixi-status"), stm: document.getElementById("refresh-stm-status") };
let refreshPollHandle = null;

function formatRefreshStatus(job, status) {
  if (status.status === "running") {
    const startedMinAgo = status.started_at ? Math.max(0, Math.round((Date.now() / 1000 - status.started_at) / 60)) : 0;
    return { text: `Running… (started ${startedMinAgo} min ago)`, cls: "running" };
  }
  if (status.status === "done") {
    return { text: "Done", cls: "done" };
  }
  if (status.status === "failed") {
    return { text: `Failed: ${status.error || "unknown error"}`, cls: "failed" };
  }
  return { text: "", cls: "" };
}

function renderRefreshStatuses(statuses) {
  let anyRunning = false;
  for (const job of REFRESH_JOBS) {
    const status = statuses[job];
    const { text, cls } = formatRefreshStatus(job, status);
    const statusEl = refreshStatusEls[job];
    statusEl.textContent = text;
    statusEl.className = `data-refresh-status${cls ? ` ${cls}` : ""}`;
    refreshButtons[job].disabled = status.status === "running";
    if (status.status === "running") anyRunning = true;
  }
  return anyRunning;
}

async function pollRefreshStatusOnce() {
  try {
    const response = await fetch("/api/admin/refresh_status");
    const statuses = await response.json();
    const anyRunning = renderRefreshStatuses(statuses);
    if (anyRunning) {
      if (!refreshPollHandle) refreshPollHandle = setInterval(pollRefreshStatusOnce, 5000);
    } else if (refreshPollHandle) {
      clearInterval(refreshPollHandle);
      refreshPollHandle = null;
    }
  } catch (err) {
    // transient fetch failure, next poll tick (or the next button click) will retry
  }
}

async function startRefresh(job) {
  try {
    const response = await fetch(`/api/admin/refresh/${job}`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      showToast(data.error || "Could not start refresh.", true);
      return;
    }
    pollRefreshStatusOnce();
  } catch (err) {
    showToast("Could not reach the server. Check your connection and try again.", true);
  }
}

refreshButtons.bixi.addEventListener("click", () => startRefresh("bixi"));
refreshButtons.stm.addEventListener("click", () => startRefresh("stm"));
pollRefreshStatusOnce(); // pick up an already-running job (e.g. started from another tab)

// planTrip(): the main "Plan trip" button handler, calls /api/plan_trip and
// hands the results to renderItinerary()
async function planTrip() {
  routeLayer.clearLayers();
  resultsDiv.innerHTML = skeletonHtml();
  const departureTime = plannedDepartureIso();

  try {
    const response = await fetch("/api/plan_trip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin, destination, allow_ebike: allowEbikeCheckbox.checked, modes: selectedModes(),
        departure_time: departureTime,
      }),
    });
    const data = await response.json();

    if (!response.ok) {
      resultsDiv.innerHTML = "";
      showToast(data.error || "Something went wrong.", true);
      return;
    }

    currentItineraries = data.itineraries;
    currentWeather = data.weather || { available: false, harsh: false, reason: null, condition: null };
    weatherAltReturnIdx = null;
    isPlannedTrip = departureTime !== null;
    weatherDebriefDiv.innerHTML = weatherDebriefHtml();
    renderItinerary(0);
  } catch (err) {
    resultsDiv.innerHTML = "";
    showToast("Could not reach the server. Check your connection and try again.", true);
  }
}

planBtn.addEventListener("click", planTrip);

// BIXI dock markers + metro/REM station markers (both always-on map layers)
function bixiIcon(level) {
  return L.divIcon({
    className: "bixi-icon",
    html: `<div class="bixi-dot">${BIXI_MARK[level] || ""}</div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

const bixiPoints = new Map(); // key -> {lat, lon}: origin, destination, trip-<i>-from/to

function setBixiPoint(key, lat, lon) {
  bixiPoints.set(key, { lat, lon });
  refreshBixiLayer();
}

function clearBixiPointsWithPrefix(prefix) {
  for (const key of bixiPoints.keys()) {
    if (key.startsWith(prefix)) bixiPoints.delete(key);
  }
}

function bixiAvailabilityText(s) {
  const classicText = `${s.classic_bikes_available} classic bike${s.classic_bikes_available === 1 ? "" : "s"}`;
  const docksText = `${s.docks_available} dock${s.docks_available === 1 ? "" : "s"}`;
  if (!allowEbikeCheckbox.checked) return `${classicText} / ${docksText}`;
  const ebikeText = `${s.ebikes_available} e-bike${s.ebikes_available === 1 ? "" : "s"}`;
  return `${classicText}, ${ebikeText} / ${docksText}`;
}

async function refreshBixiLayer() {
  const points = Array.from(bixiPoints.values());
  if (!points.length) {
    bixiLayer.clearLayers();
    return;
  }
  const results = await Promise.all(
    points.map((p) =>
      fetch(`/api/bixi_stations?lat=${p.lat}&lon=${p.lon}&radius=${BIXI_NEAR_RADIUS_M}`).then((r) => r.json())
    )
  );
  const merged = new Map();
  results.flat().forEach((s) => merged.set(s.id, s));
  bixiLayer.clearLayers();
  merged.forEach((s) => {
    L.marker([s.lat, s.lon], { icon: bixiIcon(s.level) })
      .bindTooltip(`${s.name} (${bixiAvailabilityText(s)})`, { direction: "top" })
      .bindPopup(`<strong>${s.name}</strong><br>${bixiAvailabilityText(s)}`)
      .on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        handlePointSelection(s.lat, s.lon, s.name);
      })
      .addTo(bixiLayer);
  });
}

allowEbikeCheckbox.addEventListener("change", refreshBixiLayer);

async function loadMetroStations() {
  const response = await fetch("/api/metro_stations");
  const stations = await response.json();
  stationLayer.clearLayers();
  stations.forEach((s) => {
    const lineNames = s.lines.map((l) => l.route_short_name).join(" / ");
    L.circleMarker([s.lat, s.lon], {
      radius: 6, color: `#${s.color}`, fillColor: `#${s.color}`, fillOpacity: 0.9, weight: 2,
    })
      .bindTooltip(`${s.name} (${lineNames})`, { direction: "top" })
      .on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        handlePointSelection(s.lat, s.lon, s.name);
      })
      .addTo(stationLayer);
  });
}

// Live vehicle position polling + transit-mode marker icons
function pathMidpoint(path) {
  return path[Math.floor(path.length / 2)];
}

// trip_id -> the leg's marker, repositioned in place by pollLiveVehicles() rather than
// rebuilt, so a 30s refresh doesn't flicker/reset the marker's open tooltip.
const vehicleMarkers = new Map();
let liveVehiclePollTimer = null;
const LIVE_VEHICLE_POLL_MS = 30000;

function stopLiveVehiclePolling() {
  if (liveVehiclePollTimer) {
    clearInterval(liveVehiclePollTimer);
    liveVehiclePollTimer = null;
  }
}

async function pollLiveVehicles() {
  const tripIds = [...vehicleMarkers.keys()];
  if (!tripIds.length) return;
  try {
    const response = await fetch("/api/live_vehicles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trip_ids: tripIds }),
    });
    if (!response.ok) return;
    const data = await response.json();
    (data.vehicles || []).forEach((v) => {
      const marker = vehicleMarkers.get(v.trip_id);
      if (!marker) return;
      marker.setLatLng([v.lat, v.lon]);
      const etaText = v.eta_sec !== null && v.eta_sec !== undefined && v.next_stop_name
        ? `${Math.max(0, Math.round(v.eta_sec / 60))} min to ${v.next_stop_name}`
        : marker._staticLabel;
      marker.setTooltipContent(etaText);
    });
  } catch (err) {
    // Live tracking is best-effort, keep showing the last known/static position on failure.
  }
}

function startLiveVehiclePolling() {
  stopLiveVehiclePolling();
  if (!vehicleMarkers.size) return;
  pollLiveVehicles();
  liveVehiclePollTimer = setInterval(pollLiveVehicles, LIVE_VEHICLE_POLL_MS);
}

function transitLegIcon(leg) {
  // Bus: circular badge (bus.png ships with a solid rounded-square background, clipped to a
  // circle via CSS) plus the route number next to it, since a bus logo alone doesn't say
  // which bus. Metro: the line-colored logo matching its real STM line color. REM: its own logo.
  if (leg.route_type === ROUTE_TYPE_BUS) {
    return L.divIcon({
      className: "transit-logo-icon",
      html: `<img class="bus-logo-badge" src="/static/img/bus.png"><span class="bus-logo-label">${leg.route_short_name}</span>`,
      iconSize: null,
      iconAnchor: [TRANSIT_LOGO_PX / 2, TRANSIT_LOGO_PX / 2],
    });
  }
  const file = leg.route_type === ROUTE_TYPE_REM ? "REM.png" : (METRO_LOGO_BY_COLOR[leg.route_color] || "blue_STM.png");
  return L.icon({
    className: "transit-line-logo",
    iconUrl: `/static/img/${file}`,
    iconSize: [TRANSIT_LOGO_PX, TRANSIT_LOGO_PX],
    iconAnchor: [TRANSIT_LOGO_PX / 2, TRANSIT_LOGO_PX / 2],
  });
}

// Construction/event hazard markers (shown only for the currently selected itinerary)
const HAZARD_ICON_PX = 28;

function constructionIcon() {
  // Real road-sign artwork, sized/anchored the same as eventIcon() so both read as the same
  // family of "sign" markers on the map instead of one being a plain colored dot.
  return L.icon({
    iconUrl: "/static/img/construction-sign.png",
    iconSize: [HAZARD_ICON_PX, HAZARD_ICON_PX],
    iconAnchor: [HAZARD_ICON_PX / 2, HAZARD_ICON_PX / 2],
  });
}

function eventIcon() {
  // Magenta diamond road-sign, same silhouette/size as the construction sign artwork but a
  // distinct hue (not orange, not any metro line color) and a megaphone glyph so it's
  // unmistakably a different kind of marker at a glance.
  const svg = `
    <svg width="${HAZARD_ICON_PX}" height="${HAZARD_ICON_PX}" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 1 L27 14 L14 27 L1 14 Z" fill="${EVENT_COLOR}" stroke="#1a0a12" stroke-width="1.5"/>
      <path d="M9 12.5 L14.5 9 V19 L9 15.5 Z" fill="white"/>
      <rect x="7.5" y="12" width="1.8" height="4" fill="white"/>
      <path d="M14.5 9 C18 9 20.5 11.2 20.5 14 C20.5 16.8 18 19 14.5 19" fill="none" stroke="white" stroke-width="1.6"/>
      <path d="M10.5 16.3 L11.6 19.8 C11.8 20.4 11.4 21 10.7 21 H10.2 C9.6 21 9.2 20.5 9.3 19.9 L9.8 16" fill="white"/>
    </svg>`;
  return L.divIcon({ className: "event-icon", html: svg, iconSize: [HAZARD_ICON_PX, HAZARD_ICON_PX], iconAnchor: [HAZARD_ICON_PX / 2, HAZARD_ICON_PX / 2] });
}

// Only the currently selected itinerary's own crossed closures/events are shown, not a
// city-wide dump, sourced directly from the construction_hits/event_hits already embedded in
// each bike leg by /api/plan_trip, deduped by id in case more than one leg touches the same one.
function updateHazardMarkers(itin) {
  constructionLayer.clearLayers();
  eventsLayer.clearLayers();
  const seenConstruction = new Set();
  const seenEvents = new Set();
  (itin.legs || []).forEach((leg) => {
    (leg.construction_hits || []).forEach((c) => {
      if (seenConstruction.has(c.id)) return;
      seenConstruction.add(c.id);
      L.marker([c.lat, c.lon], { icon: constructionIcon() })
        .bindTooltip(c.occupancy || c.reason || "Construction", { direction: "top" })
        .bindPopup(`<strong>Construction</strong><br>${c.occupancy || c.reason || ""}`)
        .addTo(constructionLayer);
    });
    (leg.event_hits || []).forEach((e) => {
      if (seenEvents.has(e.id)) return;
      seenEvents.add(e.id);
      L.marker([e.lat, e.lon], { icon: eventIcon() })
        .bindTooltip(e.title || "Event", { direction: "top" })
        .bindPopup(`<strong>${e.title || "Event"}</strong><br>${e.location || ""}`)
        .addTo(eventsLayer);
    });
  });
}

setInterval(refreshBixiLayer, 30000);
loadMetroStations();

// Map legend control
const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML = `
    <div class="legend-header">
      <h4>Legend</h4>
      <button class="legend-toggle" aria-expanded="true" title="Collapse legend">&minus;</button>
    </div>
    <div class="legend-body">
      <div class="legend-group">
        <h5>Transit lines</h5>
        <div class="legend-item">
          <span class="legend-dot-cluster">
            <span class="legend-dot" style="background:#00B300"></span>
            <span class="legend-dot" style="background:#D95700"></span>
            <span class="legend-dot" style="background:#FFD900"></span>
            <span class="legend-dot" style="background:#1565C0"></span>
          </span>
          Metro station
        </div>
        <div class="legend-item"><span class="legend-dot" style="background:#8E44AD"></span>REM</div>
        <div class="legend-item"><span class="legend-dot" style="background:${BUS_STOP_COLOR}"></span>Bus stop (on trip)</div>
        <div class="legend-item"><span class="legend-dot" style="background:#c0392b"></span>BIXI (plain=plenty, !=few, !!=empty)</div>
      </div>
      <div class="legend-group">
        <h5>Your route</h5>
        <div class="legend-item"><span class="legend-line" style="background:#D6001C"></span>Bike leg</div>
        <div class="legend-item"><span class="legend-line dashed" style="border-top-color:#555555"></span>Walk leg</div>
      </div>
      <div class="legend-group">
        <h5>Hazards</h5>
        <div class="legend-item"><img class="legend-icon" src="/static/img/construction-sign.png" alt="">Construction</div>
        <div class="legend-item"><svg class="legend-icon" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 1 L27 14 L14 27 L1 14 Z" fill="${EVENT_COLOR}" stroke="#1a0a12" stroke-width="1.5"/>
          <path d="M9 12.5 L14.5 9 V19 L9 15.5 Z" fill="white"/>
          <rect x="7.5" y="12" width="1.8" height="4" fill="white"/>
          <path d="M14.5 9 C18 9 20.5 11.2 20.5 14 C20.5 16.8 18 19 14.5 19" fill="none" stroke="white" stroke-width="1.6"/>
        </svg>Event</div>
      </div>
    </div>
  `;
  L.DomEvent.disableClickPropagation(div);
  div.querySelector(".legend-toggle").addEventListener("click", () => {
    const body = div.querySelector(".legend-body");
    const toggle = div.querySelector(".legend-toggle");
    const collapsed = body.classList.toggle("collapsed");
    toggle.textContent = collapsed ? "+" : "−";
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.title = collapsed ? "Expand legend" : "Collapse legend";
  });
  return div;
};
legend.addTo(map);

// Draggable sidebar resize handle
// User-draggable sidebar width. Leaflet caches its container's pixel size and won't notice a
// CSS-driven resize on its own, so invalidateSize() must be called after every width change.
const sidebarEl = document.getElementById("sidebar");
const resizeHandle = document.getElementById("sidebar-resize-handle");
const SIDEBAR_MIN_WIDTH = 280;
const SIDEBAR_MAX_WIDTH = () => window.innerWidth * 0.7;
let resizeStartX = 0;
let resizeStartWidth = 0;
let resizing = false;

resizeHandle.addEventListener("pointerdown", (e) => {
  resizing = true;
  resizeStartX = e.clientX;
  resizeStartWidth = sidebarEl.getBoundingClientRect().width;
  resizeHandle.setPointerCapture(e.pointerId);
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
});

resizeHandle.addEventListener("pointermove", (e) => {
  if (!resizing) return;
  const newWidth = resizeStartWidth + (e.clientX - resizeStartX);
  const clamped = Math.min(Math.max(newWidth, SIDEBAR_MIN_WIDTH), SIDEBAR_MAX_WIDTH());
  sidebarEl.style.width = `${clamped}px`;
  map.invalidateSize();
});

function stopResizing() {
  if (!resizing) return;
  resizing = false;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  map.invalidateSize();
}
resizeHandle.addEventListener("pointerup", stopResizing);
resizeHandle.addEventListener("pointercancel", stopResizing);
