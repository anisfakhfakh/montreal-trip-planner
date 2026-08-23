"""One-off download of the single SRTM3 elevation tile the app's whole service area fits
inside (see engine/elevation.py for how it's read). Run once during initial setup; the tile
rarely if ever needs re-downloading since terrain doesn't change."""
import argparse
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "raw" / "elevation"
DEST = RAW_DIR / "N45W074.hgt"
# SRTM3 (90m) tile covering the app's whole Montreal bbox (-73.9961, 45.3727)-(-73.2332,
# 45.7323), see PHASE3_OSRM_PLAN.md for the same bbox used for the OSM/OSRM extract. No
# NASA Earthdata login required, unlike the official SRTM30m portal.
URL = "https://srtm.kurviger.de/SRTM3/North_America/N45W074.hgt.zip"


def download_elevation_tile(force=False):
    if DEST.exists() and not force:
        print(f"[elevation] already downloaded at {DEST} (use --force to re-download)")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }
    response = requests.get(URL, headers=headers, timeout=60)
    response.raise_for_status()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".hgt")]
        if not names:
            raise RuntimeError(f"no .hgt entry found in downloaded zip: {zf.namelist()}")
        with zf.open(names[0]) as src, open(DEST, "wb") as dst:
            dst.write(src.read())
    print(f"[elevation] extracted {DEST} ({DEST.stat().st_size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Download the SRTM3 N45W074 elevation tile")
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()

    try:
        download_elevation_tile(force=args.force)
    except requests.RequestException as exc:
        print(f"[elevation] download failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
