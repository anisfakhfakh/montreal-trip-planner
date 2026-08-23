"""Thin wrapper that re-downloads STM's GTFS zip and rebuilds transit_cache.pkl from it.
Invoked as a subprocess by engine/data_refresh.py's admin-triggered STM refresh job, not
meant to be imported, only run as a script."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from download_gtfs import download_feed
from engine.graph_builder import build_transit_data


def main():
    print("Downloading fresh STM GTFS feed...")
    download_feed("stm", force=True)
    print("Rebuilding transit_cache.pkl from the fresh feed...")
    build_transit_data(force=True)
    print("STM schedule refreshed.")


if __name__ == "__main__":
    main()
