# data/

- **`data/raw/`**: Gitignored. Everything in this directory is either downloaded (GTFS zips, OSM extracts, the elevation tile) or generated (OSRM graph files, pickled caches). These files are never hand-edited or committed. If this directory is empty after a fresh checkout, check the setup section in the root [README.md](../README.md) to populate it.
- **`data/scripts/`**: The ETL and precompute pipeline that produces everything in `data/raw/`. See [data/scripts/README.md](scripts/README.md) for details.

## What lands in `data/raw/` and who produces it

| File(s) | Produced by |
|---|---|
| `stm_gtfs.zip`, `rem_gtfs.zip` | `data/scripts/download_gtfs.py` |
| `montreal.osm.pbf`, `montreal.osrm*` (foot + bike graphs) | Manual OSM extract + `osrm-extract`/`osrm-contract` (see `docker-compose.yml` and the root README's setup steps) |
| `elevation/N45W074.hgt` | `data/scripts/precompute_elevation.py` |
| `transit_cache.pkl` | `engine/graph_builder.py`, built from the GTFS zips above |
| `walk_graph_cache.pkl` | `data/scripts/precompute_walk_graph.py`, built from the OSRM graphs and elevation tile above |