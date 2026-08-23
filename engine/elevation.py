"""Local SRTM3 (90m) elevation lookup for the app's Montreal service-area bbox, backed by a
single downloaded tile (N45W074) that covers the entire existing bbox used for the OSM/OSRM
extract: (-73.9961, 45.3727) to (-73.2332, 45.7323), see PHASE3_OSRM_PLAN.md.

No GDAL/rasterio dependency: .hgt is a trivial raw binary grid, 1201x1201 big-endian signed
16-bit ints for SRTM3. Row 0 = north edge (lat 46), row 1200 = south edge (lat 45); col 0 =
west edge (lon -74), col 1200 = east edge (lon -73). Nearest-neighbor lookup only, SRTM3's
own ~90m grid spacing and ~6-9m vertical RMSE already dominate precision.

Only ever imported by data/scripts/precompute_walk_graph.py, not by app.py/router.py at
request time, bike edges that fall through to the live-OSRM/haversine path instead of the
cache degrade gracefully to "assume flat" (see engine/walk_graph.py), no runtime dependency
on this module or the tile being present.
"""
from pathlib import Path

import numpy as np

HGT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "elevation" / "N45W074.hgt"
GRID_SIZE = 1201
TILE_NORTH_LAT = 46  # row 0
TILE_WEST_LON = -74  # col 0

_grid = np.fromfile(HGT_PATH, dtype=">i2").reshape(GRID_SIZE, GRID_SIZE) if HGT_PATH.exists() else None


def elevation_m(lat, lon):
    """Nearest-neighbor elevation in meters at (lat, lon)."""
    if _grid is None:
        raise FileNotFoundError(
            f"Elevation tile not found at {HGT_PATH}, run "
            f"`python data/scripts/precompute_elevation.py` first."
        )
    row = min(max(round((TILE_NORTH_LAT - lat) * (GRID_SIZE - 1)), 0), GRID_SIZE - 1)
    col = min(max(round((lon - TILE_WEST_LON) * (GRID_SIZE - 1)), 0), GRID_SIZE - 1)
    return float(_grid[row, col])
