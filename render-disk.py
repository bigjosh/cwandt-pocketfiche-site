#!/usr/bin/env python3
"""Render a single full-resolution PNG of the current Pocket Fiche disk.

Reads the live claimed-parcel list and the public zoom-6 tile images from the
server (default https://pf.josh.com) and composites every parcel at its actual
grid location -- no packing or rearrangement -- onto the canonical gold fiche
disk. This is the faithful-snapshot companion to pack_parcels.py, which instead
repacks parcels into the smallest possible disk.

The geometry, coordinate conventions, and gold-disk look are lifted from
pack_parcels.py; the "composite every parcel at its real (row, col)" idea is
from obp.py.

Requirements:
- requests:  pip install requests
- Pillow:    pip install Pillow
- pyoxipng (optional, better compression): pip install pyoxipng
  Falls back to Pillow's own PNG compression when not installed.

Usage:
  python render-disk.py                       # full-res gold disk from pf.josh.com
  python render-disk.py --scale 60            # quick small preview
  python render-disk.py --output-file disk.png --no-compress
"""

from __future__ import annotations

import argparse
import math
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

try:
    import oxipng
except ImportError:
    oxipng = None

# We intentionally build very large images (~19,900 px square at full res), so
# disable Pillow's decompression-bomb guard for this tool.
Image.MAX_IMAGE_PIXELS = None


GRID_SIZE = 38
ORIGINAL_CENTER = (GRID_SIZE - 1) / 2          # 18.5 -- cell-center origin
ORIGINAL_EDGE_CENTER = GRID_SIZE / 2           # 19.0 -- cell-edge origin
OFFSET_AT_ZOOM_6 = (2**6 - GRID_SIZE) // 2     # 13  -- centers 38x38 in the 64x64 zoom-6 grid
TILE_SIZE = 500                                # native pixels per parcel tile

DEFAULT_PARCELS_URL = "https://pf.josh.com/upload/cgi-bin/app.py?command=get-parcels"
DEFAULT_TILE_BASE_URL = "https://pf.josh.com/world/images/6"

DISK_FILL = (183, 135, 39, 255)                # canonical gold fiche color
DISK_OUTLINE = (255, 255, 255, 180)


def row_letters_to_index(letters: str) -> int:
    result = 0
    for char in letters.upper():
        result = (result * 26) + (ord(char) - ord("A") + 1)
    return result - 1


def parse_location(location: str) -> tuple[int, int]:
    match = re.match(r"^([A-Za-z]+)(\d+)$", location.strip())
    if not match:
        raise ValueError(f"Invalid parcel location: {location}")
    return row_letters_to_index(match.group(1)), int(match.group(2)) - 1


def cell_edge_radius_squared(x: float, y: float) -> float:
    return max((x + dx) ** 2 + (y + dy) ** 2 for dx in (0, 1) for dy in (0, 1))


def canonical_claimable_edge_radius() -> float:
    """Edge radius (in parcel units) of the canonical claimable disk.

    Cells are claimable when their center is within 19 parcels of the grid
    center; this returns the radius that tightly contains every such cell, so a
    disk drawn at this radius holds every legitimately-claimed parcel.
    """
    max_radius_squared = 0.0
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            if math.hypot(row - ORIGINAL_CENTER, col - ORIGINAL_CENTER) <= 19:
                x = col - ORIGINAL_EDGE_CENTER
                y = row - ORIGINAL_EDGE_CENTER
                max_radius_squared = max(max_radius_squared, cell_edge_radius_squared(x, y))
    return math.sqrt(max_radius_squared)


def fetch_live_parcels(parcels_url: str) -> list[str]:
    response = requests.get(parcels_url, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "success" or not isinstance(data.get("parcels"), list):
        raise RuntimeError(f"Unexpected parcel API response: {data}")
    return sorted({str(location).strip().upper() for location in data["parcels"]})


def tile_url_for_location(tile_base_url: str, location: str) -> str:
    row, col = parse_location(location)
    tile_x = col + OFFSET_AT_ZOOM_6
    tile_y = OFFSET_AT_ZOOM_6 + (GRID_SIZE - 1) - row
    return f"{tile_base_url.rstrip('/')}/{tile_x}/{tile_y}.png"


def download_tiles(labels: list[str], tile_base_url: str, image_dir: Path, refresh: bool = False) -> dict:
    image_dir.mkdir(parents=True, exist_ok=True)
    stats: Counter = Counter()
    session = requests.Session()

    for location in labels:
        output_path = image_dir / f"{location}.png"
        if not refresh and output_path.exists() and output_path.stat().st_size > 100:
            stats["reused"] += 1
            continue
        url = tile_url_for_location(tile_base_url, location)
        try:
            response = session.get(url, timeout=20)
            if response.status_code == 200 and "image" in response.headers.get("Content-Type", ""):
                output_path.write_bytes(response.content)
                if len(response.content) > 100:
                    stats["downloaded"] += 1
                else:
                    stats["empty_or_missing"] += 1
            else:
                stats["failed"] += 1
        except requests.RequestException:
            stats["failed"] += 1

    return dict(stats)


def load_font(size: int):
    for font_name in ("arial.ttf", "consola.ttf"):
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def render_disk(
    labels: list[str],
    radius: float,
    image_dir: Path,
    scale: int,
    mark_missing: bool = False,
) -> tuple[Image.Image, dict]:
    """Composite each parcel at its true grid position onto the gold disk."""
    margin = max(16, int(scale * 0.12))
    diameter_px = math.ceil(2 * radius * scale)
    canvas_size = diameter_px + margin * 2
    center_px = margin + radius * scale

    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    disk_box = [margin, margin, margin + diameter_px, margin + diameter_px]
    draw.ellipse(disk_box, fill=DISK_FILL, outline=DISK_OUTLINE, width=max(1, scale // 80))

    missing: list[str] = []
    out_of_bounds: list[str] = []
    font = load_font(max(10, scale // 7))

    for location in labels:
        row, col = parse_location(location)
        # Original (un-packed) centered-cell corner coords; +y is up.
        x = col - ORIGINAL_EDGE_CENTER
        y = row - ORIGINAL_EDGE_CENTER
        left = round(center_px + x * scale)
        top = round(center_px - (y + 1) * scale)
        tile_path = image_dir / f"{location}.png"

        if tile_path.exists() and tile_path.stat().st_size > 100:
            tile = Image.open(tile_path).convert("RGBA")
            if tile.size != (scale, scale):
                tile = tile.resize((scale, scale), Image.Resampling.NEAREST)
            if 0 <= left <= canvas_size - scale and 0 <= top <= canvas_size - scale:
                image.alpha_composite(tile, (left, top))
            else:
                # Safety net for any claim outside the canonical disk: paste()
                # clips gracefully where alpha_composite() would raise.
                image.paste(tile, (left, top), tile)
                out_of_bounds.append(location)
        else:
            missing.append(location)
            if mark_missing:
                draw.rectangle(
                    [left, top, left + scale - 1, top + scale - 1],
                    outline=(200, 0, 0, 200),
                    width=max(1, scale // 80),
                )
                draw.text(
                    (left + scale / 2, top + scale / 2),
                    location, anchor="mm", fill=(160, 0, 0, 255), font=font,
                )

    return image, {"missing": missing, "out_of_bounds": out_of_bounds, "canvas_size": canvas_size}


def compress_png_with_oxipng(png_path: Path) -> tuple[int, int]:
    """Losslessly compress a PNG in place via oxipng, with atomic replacement."""
    original_size = png_path.stat().st_size
    fd, temp_name = tempfile.mkstemp(dir=png_path.parent, suffix=".png")
    temp_path = Path(temp_name)
    os.close(fd)
    try:
        oxipng.optimize(png_path, temp_path)
        compressed_size = temp_path.stat().st_size
        temp_path.replace(png_path)
        return original_size, compressed_size
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a full-res PNG of the live Pocket Fiche disk (no packing)."
    )
    parser.add_argument("--parcels-url", default=DEFAULT_PARCELS_URL)
    parser.add_argument("--tile-base-url", default=DEFAULT_TILE_BASE_URL)
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--cache-dir", default="scratch/disk-tiles",
                        help="Where downloaded tiles are cached and reused across runs.")
    parser.add_argument("--scale", type=int, default=TILE_SIZE,
                        help="Rendered pixels per parcel (default 500 = full res).")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-download tiles even if already cached.")
    parser.add_argument("--mark-missing", action="store_true",
                        help="Outline claimed parcels whose tile failed to download.")
    parser.add_argument("--no-compress", action="store_true",
                        help="Skip the final PNG compression pass.")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = Path(args.output_file) if args.output_file else Path("scratch") / f"disk-{timestamp}.png"
    image_dir = Path(args.cache_dir)

    print(f"Fetching live parcel list from {args.parcels_url}")
    labels = fetch_live_parcels(args.parcels_url)
    print(f"Claimed parcels: {len(labels)}")

    print(f"Downloading zoom-6 tiles into {image_dir} (cache reuse: {not args.refresh}) ...")
    download_stats = download_tiles(labels, args.tile_base_url, image_dir, refresh=args.refresh)
    print(f"  tiles: {download_stats}")

    radius = canonical_claimable_edge_radius()
    print(f"Rendering at {args.scale}px/parcel (disk radius {radius:.3f} parcels) ...")
    image, render_stats = render_disk(labels, radius, image_dir, args.scale, mark_missing=args.mark_missing)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    canvas = render_stats["canvas_size"]
    print(f"Saving {output_file} ({canvas}x{canvas}px) ...")
    if args.no_compress:
        image.save(output_file, "PNG")
    elif oxipng is not None:
        image.save(output_file, "PNG")  # fast save; oxipng does the compression below
        print("Compressing with oxipng ...")
        before, after = compress_png_with_oxipng(output_file)
        pct = (before - after) / before * 100 if before else 0
        print(f"  {before:,} -> {after:,} bytes ({pct:+.1f}%)")
    else:
        print("pyoxipng not installed; using Pillow's PNG compression.")
        image.save(output_file, "PNG", optimize=True)

    file_size = output_file.stat().st_size
    rendered = len(labels) - len(render_stats["missing"])
    print()
    print("Done.")
    print(f"Output: {output_file} ({file_size / (1024 * 1024):.2f} MB)")
    print(f"Parcels rendered: {rendered} / {len(labels)}")
    if render_stats["missing"]:
        print(f"Missing/empty tiles ({len(render_stats['missing'])}): {', '.join(render_stats['missing'])}")
    if render_stats["out_of_bounds"]:
        print(f"Claims outside the canonical disk ({len(render_stats['out_of_bounds'])}): "
              f"{', '.join(render_stats['out_of_bounds'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
