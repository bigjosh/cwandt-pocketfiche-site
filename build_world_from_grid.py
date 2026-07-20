#!/usr/bin/env python3
"""Build the docs/world/images tile pyramid from the final full-grid bitmap.

Takes the final 19000x19000 1-bit grid bitmap (white = ON dots, black = OFF)
and slices it into the same tile pyramid layout that build_world.py produces:
docs/world/images/{z}/{x}/{y}.png, zooms 0-6, 500px tiles, with the 38x38
parcel grid centered in the 64x64 zoom-6 tile space.

Tiles are written as opaque-white-on-transparent PNGs (the gold disk in the
viewer shows through the OFF pixels), exactly like the live site's tiles.
Parcels that are entirely OFF are skipped so they 404 in the viewer and the
bare gold disk shows -- same behavior as unclaimed parcels today.

The source bitmap fills the corners between the artwork disk and the square
edge of the image with a 16x16 halftone screen (41.4% ON) that reads as flat
grey. Parcels outside --clip-radius are dropped so the gold disk shows there
instead. The default 19.0 was verified against this bitmap: every parcel that
is nothing but the screen sits at radius >= 19.04 and every parcel holding
real artwork sits at radius <= 18.83, so the cut is unambiguous. Note that the
same halftone appears *inside* real artwork (it is how photos were reduced to
1-bit), so the screen pattern alone must never be used to identify filler.

The labels pyramid (docs/world/labels) is left untouched.

Usage:
  python build_world_from_grid.py --grid-file path/to/grid.bmp [--output-dir docs/world]
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from pathlib import Path

from PIL import Image

from build_world import GRID_SIZE, MAX_ZOOM, MIN_ZOOM, OFFSET, TILE_SIZE, create_zoom_level

# The grid bitmap is intentionally huge; disable the decompression-bomb guard.
Image.MAX_IMAGE_PIXELS = None

EXPECTED_SIZE = GRID_SIZE * TILE_SIZE  # 19000


def build_zoom_6(grid: Image.Image, images_dir: Path, clip_radius: float) -> tuple[int, int, int]:
    """Slice the grid bitmap into zoom-6 tiles. Returns (written, empty, clipped)."""
    zoom_dir = images_dir / str(MAX_ZOOM)
    solid = Image.new("L", (TILE_SIZE, TILE_SIZE), 255)
    center = (GRID_SIZE - 1) / 2

    written = 0
    empty = 0
    clipped = 0
    for row_top in range(GRID_SIZE):          # 0 = top of bitmap = row AL
        for col in range(GRID_SIZE):          # 0 = left of bitmap = column 1
            if math.hypot(row_top - center, col - center) > clip_radius:
                clipped += 1                  # corner halftone filler -> bare gold disk
                continue

            box = (col * TILE_SIZE, row_top * TILE_SIZE,
                   (col + 1) * TILE_SIZE, (row_top + 1) * TILE_SIZE)
            crop = grid.crop(box)
            if crop.getbbox() is None:        # no ON pixels -> 404 in viewer
                empty += 1
                continue

            # ON pixels become opaque white, OFF pixels transparent.
            tile = Image.merge("RGBA", (solid, solid, solid, crop))

            tile_x = OFFSET + col
            tile_y = OFFSET + row_top
            tile_dir = zoom_dir / str(tile_x)
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile.save(tile_dir / f"{tile_y}.png", "PNG")
            written += 1

    return written, empty, clipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build docs/world/images pyramid from the final grid bitmap."
    )
    parser.add_argument("--grid-file", required=True,
                        help="Path to the 19000x19000 1-bit grid bitmap (white=ON).")
    parser.add_argument("--output-dir", default="docs/world",
                        help="World output directory (default: docs/world).")
    parser.add_argument("--clip-radius", type=float, default=19.0,
                        help="Drop parcels whose center is farther than this many parcels "
                             "from the grid center, removing the corner halftone filler "
                             "(default: 19.0).")
    args = parser.parse_args()

    grid_path = Path(args.grid_file)
    output_dir = Path(args.output_dir)
    images_dir = output_dir / "images"

    print(f"Loading {grid_path} ...")
    grid = Image.open(grid_path).convert("L")
    if grid.size != (EXPECTED_SIZE, EXPECTED_SIZE):
        print(f"ERROR: expected {EXPECTED_SIZE}x{EXPECTED_SIZE}, got {grid.size}")
        return 1

    # Snap to strict 0/255 in case the source ever isn't exactly 1-bit.
    grid = grid.point(lambda v: 255 if v >= 128 else 0)

    if images_dir.exists():
        print(f"Removing old {images_dir} ...")
        shutil.rmtree(images_dir)

    print(f"Slicing zoom {MAX_ZOOM} tiles ({GRID_SIZE}x{GRID_SIZE} parcels, "
          f"clip radius {args.clip_radius}) ...")
    written, empty, clipped = build_zoom_6(grid, images_dir, args.clip_radius)
    print(f"  {written} tiles written, {empty} all-OFF parcels skipped, "
          f"{clipped} corner-filler parcels clipped")

    for zoom in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        print(f"Building zoom {zoom} ...")
        create_zoom_level(zoom, images_dir / str(zoom))

    total = sum(1 for _ in images_dir.rglob("*.png"))
    print(f"Done. {total} tiles in {images_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
