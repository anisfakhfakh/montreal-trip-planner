# static/

Frontend assets served directly by Flask. There is no build step or bundler. `templates/index.html` loads these as standard `<script>` and `<link>` tags alongside the Leaflet CDN scripts.

| Path | Purpose |
|---|---|
| `js/map.js` | Contains all client-side logic in a single file (~1400 lines). Section-header comments mark feature areas like map setup, address search, itinerary rendering, and UI controls. You can search for `====` to jump between sections. It communicates with the backend exclusively through the `/api/*` endpoints documented in the root [ARCHITECTURE.md](../ARCHITECTURE.md). |
| `css/style.css` | All styling in a single file (~960 lines). A `:root` custom-property block at the top defines color and spacing tokens. The rest is organized by UI component, matching the order they appear in `index.html` and `map.js`, separated by comment dividers. |
| `img/` | Mode and line icons (BIXI, REM, metro line colors, bus, construction sign, favicon). These are referenced by `map.js` for map markers, itinerary leg icons, and the legend control. |

## Why no framework or build step

The app is a single-page map tool with one primary view and no client-side routing. Introducing a bundler or framework would add complex build tooling without providing enough structural benefit for a project of this scale. See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full reasoning.