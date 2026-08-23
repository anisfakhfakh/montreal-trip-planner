"""One-off/on-demand download of the static GTFS feeds (STM buses+metro, REM) into data/raw/.
Run manually (`python data/scripts/download_gtfs.py`) or invoked by refresh_stm.py as part of
the admin-triggered STM refresh job (see engine/data_refresh.py)."""
import argparse
import os
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"

FEEDS = {
    "stm": {
        "url": "https://www.stm.info/sites/default/files/gtfs/gtfs_stm.zip",
        "dest": RAW_DIR / "stm_gtfs.zip",
        # STM's edge WAF returns an HTML error page without a Referer from their own site.
        "headers": {"Referer": "https://www.stm.info/en/about/developers"},
    },
    "rem": {
        "url": "https://gtfs.gpmmom.ca/gtfs/gtfs.zip",
        "dest": RAW_DIR / "rem_gtfs.zip",
        "headers": {},
    },
}


def download_feed(name, force=False):
    feed = FEEDS[name]
    if feed["dest"].exists() and not force:
        print(f"[{name}] already downloaded at {feed['dest']} (use --force to re-download)")
        return

    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }
    headers = {**default_headers, **feed["headers"]}
    response = requests.get(feed["url"], headers=headers, timeout=60)
    response.raise_for_status()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # Write-then-rename instead of a direct write_bytes(), os.replace is atomic on both Windows
    # and POSIX, so a concurrent reader (or a second refresh job racing on this same path) only
    # ever sees the old complete file or the new complete file, never a partial download.
    tmp_path = feed["dest"].with_suffix(f"{feed['dest'].suffix}.tmp{os.getpid()}")
    tmp_path.write_bytes(response.content)
    os.replace(tmp_path, feed["dest"])
    print(f"[{name}] downloaded {len(response.content):,} bytes to {feed['dest']}")


def main():
    parser = argparse.ArgumentParser(description="Download STM and REM static GTFS feeds")
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    parser.add_argument("--feed", choices=list(FEEDS), help="only download this one feed (default: all)")
    args = parser.parse_args()

    names = [args.feed] if args.feed else list(FEEDS)
    for name in names:
        try:
            download_feed(name, force=args.force)
        except requests.RequestException as exc:
            print(f"[{name}] download failed: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
