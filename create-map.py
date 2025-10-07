#!/usr/bin/env python3
"""
Create a map.json from the tiles/ directory.

Scans files like tiles/tile-H4.png and produces a JSON object mapping
coordinates (e.g., "H4") to { "claimed": true } so it can be directly
used as a JS dictionary/object.

Additionally, it appends entries for ALL unclaimed tiles whose centers lie
INSIDE the circular claimable area, with { "claimed": false }. These
unclaimed entries are added after the claimed ones.

Usage:
  python create-map.py [--tiles-dir tiles] [--output map.json] [--minify]
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, Optional

# Grid and radius constants (mirroring download_tiles.py)
TILE_SIZE = 500
COLS = 38
ROWS = 38
WIDTH = COLS * TILE_SIZE
HEIGHT = ROWS * TILE_SIZE
CLAIM_RADIUS_PX = 9500
RADIUS_CENTER_X = WIDTH / 2
RADIUS_CENTER_Y = HEIGHT / 2

# Matches filenames like: tile-H4.png, tile-AA12.png (case-insensitive on extension)
FILENAME_RE = re.compile(r"^tile-([A-Za-z]+)(\d+)\.(?:png)$", re.IGNORECASE)


def parse_coordinate(filename: str) -> Optional[str]:
    """Extract coordinate like 'H4' from a filename like 'tile-H4.png'."""
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    row_letters = m.group(1).upper()
    col_number = m.group(2)
    return f"{row_letters}{col_number}"


def col_to_letters(col: int) -> str:
    """Convert 0-based index to Excel-style letters: 0->A, 25->Z, 26->AA, ..."""
    result = ""
    col += 1  # Excel columns are 1-indexed
    while col > 0:
        col -= 1
        result = chr(65 + (col % 26)) + result
        col //= 26
    return result


def parcel_center(col: int, row: int):
    """Center coordinates of a parcel in pixels."""
    x = col * TILE_SIZE + TILE_SIZE / 2
    y = row * TILE_SIZE + TILE_SIZE / 2
    return (x, y)


def is_inside_radius(col: int, row: int) -> bool:
    """Check if parcel center is within the claimable radius."""
    x, y = parcel_center(col, row)
    dx = x - RADIUS_CENTER_X
    dy = y - RADIUS_CENTER_Y
    distance = math.hypot(dx, dy)
    return distance <= CLAIM_RADIUS_PX


def build_map(tiles_dir: Path) -> Dict[str, Dict[str, bool]]:
    """Iterate tile files and build the mapping.

    Produces:
      { "H4": {"claimed": true}, ... , "A1": {"claimed": false}, ... }

    - First, adds claimed tiles found in the tiles/ directory.
    - Then, appends unclaimed tiles for every grid cell whose center is inside
      the circular claimable area and not already present as claimed.
    """
    if not tiles_dir.exists() or not tiles_dir.is_dir():
        raise FileNotFoundError(f"Tiles directory not found: {tiles_dir}")

    mapping: Dict[str, Dict[str, bool]] = {}

    # Iterate deterministically
    for entry in sorted(tiles_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        coord = parse_coordinate(entry.name)
        if coord is None:
            continue
        mapping[coord] = {"claimed": True}

    # Append unclaimed entries for tiles inside the radius, in a stable order
    for row in range(ROWS):
        row_letters = col_to_letters(row)
        for col in range(COLS):
            if not is_inside_radius(col, row):
                continue
            coord = f"{row_letters}{col}"
            if coord not in mapping:
                mapping[coord] = {"claimed": False}

    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Create map.json from tile images")
    parser.add_argument(
        "--tiles-dir",
        default="tiles",
        help="Directory containing tile images (default: tiles)",
    )
    parser.add_argument(
        "--output",
        default="map.json",
        help="Output JSON file path (default: map.json)",
    )
    parser.add_argument(
        "--minify",
        action="store_true",
        help="Write compact JSON without spaces",
    )

    args = parser.parse_args()

    tiles_path = Path(args.tiles_dir)
    output_path = Path(args.output)

    mapping = build_map(tiles_path)

    indent = None if args.minify else 2
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=indent, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(mapping)} entries to {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
