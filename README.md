# Montreal Trip Planner

A multi-modal trip planner for Montreal that combines STM buses and metro, REM light rail, BIXI bikes, and walking. Route anywhere in the city or its suburbs using public transit and the bike-share network. 

You can restrict certain transport modes, set a maximum walking time per leg, and sort results by total duration, number of transfers, or risk score. The app also warns you about nearby construction or live events that might affect your trip.

## Demo



https://github.com/user-attachments/assets/330c1a04-ec87-4f7d-a604-dc1371545d76



This project is open source under the [MIT License](LICENSE). 

Check out [ARCHITECTURE.md](ARCHITECTURE.md) for a breakdown of how the project is built, and [ROUTING_ALGORITHM.md](ROUTING_ALGORITHM.md) for a deep dive into the algorithm behind the routing estimates.

## Tech stack

*   **Backend:** Python 3 and Flask. There is no database. Schedule and graph data are precomputed offline and loaded directly into memory at startup (see [ARCHITECTURE.md](ARCHITECTURE.md#3-backend)).
*   **Routing:** Self-hosted [OSRM](https://project-osrm.org/) via Docker for accurate street distances, wrapped in a custom Dijkstra-based multi-modal search (see [ARCHITECTURE.md](ARCHITECTURE.md#4-algorithmic-design)).
*   **Frontend:** Vanilla JavaScript and [Leaflet](https://leafletjs.com/).
*   **Data sources:** STM Metro and REM static GTFS, STM GTFS-RT (live buses), BIXI GBFS, Environment Canada weather, Montreal Open Data (construction and events), and Nominatim for geocoding.

## Prerequisites

*   Python 3.10+
*   [Docker](https://www.docker.com/) (to run the OSRM routing containers)
*   An STM developer API key (free). This is used for real-time bus positions and delays. The app will still run on static schedules if you don't provide one. You can trigger updates for live schedule data and bike dock positions directly from the app, though rebuilding the search graph takes a bit of time.

## Setup

1. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API keys**
   ```bash
   cp .env.example .env
   ```
   Add your `STM_API_KEY` (highly recommended for live data; you can grab one from the [STM developer portal](https://www.stm.info/en/about/developers)). 
   
   *Note:* The `GOOGLE_MAPS_ROUTES_API_KEY` is only required if you want to run the validation scripts in the `testing/` folder with the `--with-google` comparison enabled. It is not required to run the main app.

3. **Download and build the required data**
   See [data/README.md](data/README.md) for file details and [data/scripts/README.md](data/scripts/README.md) for script documentation.
   ```bash
   python data/scripts/download_gtfs.py
   python data/scripts/precompute_elevation.py
   ```
   Next, extract a Montreal OpenStreetMap (OSM) region into `data/raw/osm/foot/` and `data/raw/osm/bike/`. Build the OSRM graphs using `osrm-extract`, `osrm-partition`, and `osrm-customize` (one pass per profile). Check `docker-compose.yml` for the exact paths the containers expect. Finally, run:
   ```bash
   python data/scripts/precompute_walk_graph.py
   ```
   *Note: This final script resolves tens of thousands of routing pairs. It is slow and usually takes 10 to 15 minutes to complete.*

4. **Start the OSRM routing containers**
   ```bash
   docker compose up -d
   ```

5. **Run the app**
   ```bash
   python app.py
   ```
   Open `http://localhost:5000` in your browser.

## Keeping data fresh

You can update the STM schedule or BIXI walk-graph cache on the fly. Just use the buttons under "Data freshness" in the app's sidebar to trigger background jobs without needing to restart the server. See [ARCHITECTURE.md](ARCHITECTURE.md#3-backend) for details on how this works.

## Validating routing changes

Instead of a traditional unit test suite, we validate routing and scoring changes against a fixed set of real-world routes. Check out [testing/README.md](testing/README.md) for more info on how to run these comparisons, or view the [live Route Validation Log](https://claude.ai/code/artifact/648f84a8-fa54-41b1-a291-ce7e92bea8a1) directly.
