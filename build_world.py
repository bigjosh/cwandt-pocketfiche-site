#!/usr/bin/env python3
"""
Build World Tile Pyramid

Reads 500x500 parcel PNG images from parcels/ and creates a tile pyramid
in world/ with structure world/{z}/{x}/{y}.png following OpenStreetMap conventions.

At zoom level 6: 1:1 mapping (one tile per parcel, no scaling)
At zoom level 0: single 500x500 tile containing entire world scaled 64x

Usage:
  python build_world.py [--parcels-dir parcels] [--output-dir world]
"""

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow library required. Install with: pip install Pillow")
    sys.exit(1)


# Constants
TILE_SIZE = 500  # All tiles are 500x500 pixels
MAX_ZOOM = 6     # Zoom level where parcels are 1:1 with tiles
MIN_ZOOM = 0     # Zoom level with single tile covering entire world
GRID_SIZE = 38   # World is 38x38 parcels
MAX_TILES_AT_ZOOM_6 = 2 ** MAX_ZOOM  # 64x64 tiles at zoom 6
OFFSET = (MAX_TILES_AT_ZOOM_6 - GRID_SIZE) // 2  # Center the 38x38 world in 64x64 grid

# Matches filenames like: tile-H4.png, tile-AA12.png, tile-R17.png
FILENAME_RE = re.compile(r"^tile-([A-Za-z]+)(\d+)\.png$", re.IGNORECASE)


def letters_to_row(letters: str) -> int:
    """Convert Excel-style letters to 0-based row index.
    A->0, B->1, ..., Z->25, AA->26, AB->27, ..., AL->37
    """
    result = 0
    for char in letters.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def parse_parcel_filename(filename: str) -> Optional[Tuple[int, int]]:
    """Parse parcel filename to extract (row, col) coordinates.
    
    Args:
        filename: e.g., "tile-H4.png" or "tile-R17.png"
        Format is "tile-{ROW_LETTERS}{COL_NUMBER}.png"
        where ROW_LETTERS (A-AL) and COL_NUMBER (0-based) identify the parcel.
        Note: A1 is at top-left, AL38 is at bottom-right (per README).
    
    Returns:
        (row, col) as 0-based indices, or None if invalid
        row: 0=A (top), 37=AL (bottom)
        col: 0-based column number from filename
    """
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    
    row_letters = m.group(1).upper()
    try:
        col = int(m.group(2))
    except ValueError:
        return None
    
    row = letters_to_row(row_letters)
    return (row, col)


def load_parcels(parcels_dir: Path) -> Dict[Tuple[int, int], Image.Image]:
    """Load all parcel images from directory.
    
    Returns:
        Dictionary mapping (row, col) -> PIL Image
    """
    if not parcels_dir.exists() or not parcels_dir.is_dir():
        raise FileNotFoundError(f"Parcels directory not found: {parcels_dir}")
    
    parcels = {}
    for entry in sorted(parcels_dir.iterdir()):
        if not entry.is_file() or not entry.suffix.lower() == '.png':
            continue
        
        coords = parse_parcel_filename(entry.name)
        if coords is None:
            print(f"⚠️  Skipping unrecognized filename: {entry.name}")
            continue
        
        try:
            img = Image.open(entry)
            if img.size != (TILE_SIZE, TILE_SIZE):
                print(f"⚠️  Warning: {entry.name} is {img.size}, expected {TILE_SIZE}x{TILE_SIZE}")
            parcels[coords] = img.convert('RGBA')  # Ensure RGBA mode
            print(f"✅ Loaded {entry.name} -> row={coords[0]}, col={coords[1]}")
        except Exception as e:
            print(f"❌ Failed to load {entry.name}: {e}")
    
    return parcels


def create_zoom_6_tiles(parcels: Dict[Tuple[int, int], Image.Image], output_dir: Path):
    """Create zoom level 6 tiles (1:1 with parcels, no scaling).
    
    At zoom 6 in standard slippy map: 64x64 tiles (2^6 = 64)
    Our 38x38 parcel world is centered within this grid.
    - Offset of 13 on each side: (64-38)/2 = 13
    - A1 (row=0, col=0) at bottom-left maps to tile (13, 50)
    - AL38 (row=37, col=37) at top-right maps to tile (50, 13)
    - Y-axis is inverted: row=0 (bottom) → high y, row=37 (top) → low y
    """
    zoom_dir = output_dir / "6"
    
    for (row, col), img in parcels.items():
        # Center the parcel world within the 64x64 grid
        tile_x = col + OFFSET
        # Invert Y: A (row=0) is at bottom, so gets high y value
        tile_y = OFFSET + (GRID_SIZE - 1) - row
        
        tile_dir = zoom_dir / str(tile_x)
        tile_dir.mkdir(parents=True, exist_ok=True)
        
        tile_path = tile_dir / f"{tile_y}.png"
        img.save(tile_path, 'PNG')
        print(f"  Saved {tile_path.relative_to(output_dir)} (parcel row={row}, col={col})")
    
    print(f"✅ Created {len(parcels)} tiles at zoom level 6")


def get_tile_bounds(zoom: int, x: int, y: int) -> Tuple[int, int, int, int]:
    """Get the parcel coordinate bounds covered by a tile at given zoom.
    
    Returns:
        (col_min, row_min, col_max, row_max) in parcel coordinates
    """
    # Number of parcels covered by one tile at this zoom
    parcels_per_tile = 2 ** (MAX_ZOOM - zoom)
    
    col_min = x * parcels_per_tile
    row_min = y * parcels_per_tile
    col_max = col_min + parcels_per_tile
    row_max = row_min + parcels_per_tile
    
    return (col_min, row_min, col_max, row_max)


def create_tile_from_children(zoom: int, x: int, y: int, output_dir: Path) -> Optional[Image.Image]:
    """Create a tile by combining and scaling 4 child tiles from zoom+1.
    
    Returns:
        PIL Image if tile was created, None if no child tiles exist
    """
    child_zoom = zoom + 1
    child_zoom_dir = output_dir / str(child_zoom)
    
    # Each tile at zoom Z corresponds to 4 tiles at zoom Z+1
    child_tiles = []
    for dy in range(2):
        row = []
        for dx in range(2):
            child_x = x * 2 + dx
            child_y = y * 2 + dy
            
            child_path = child_zoom_dir / str(child_x) / f"{child_y}.png"
            if child_path.exists():
                row.append(Image.open(child_path))
            else:
                # Create transparent placeholder
                row.append(Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0)))
        
        child_tiles.append(row)
    
    # Check if all children are empty (transparent)
    all_empty = all(
        img.getbbox() is None 
        for row in child_tiles 
        for img in row
    )
    if all_empty:
        return None
    
    # Combine 4 tiles into one 1000x1000 image
    combined = Image.new('RGBA', (TILE_SIZE * 2, TILE_SIZE * 2), (0, 0, 0, 0))
    for dy in range(2):
        for dx in range(2):
            combined.paste(child_tiles[dy][dx], (dx * TILE_SIZE, dy * TILE_SIZE))
    
    # Scale down to TILE_SIZE x TILE_SIZE using high-quality resampling (anti-aliasing)
    scaled = combined.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.LANCZOS)
    
    return scaled


def create_zoom_level(zoom: int, output_dir: Path):
    """Create all tiles for a given zoom level by scaling from zoom+1.
    
    Standard slippy map: at zoom Z, there are 2^Z tiles per side.
    We only create tiles that have content (where parcels exist).
    """
    zoom_dir = output_dir / str(zoom)
    tiles_at_zoom = 2 ** zoom
    
    created_count = 0
    for x in range(tiles_at_zoom):
        for y in range(tiles_at_zoom):
            tile = create_tile_from_children(zoom, x, y, output_dir)
            if tile is not None:
                tile_dir = zoom_dir / str(x)
                tile_dir.mkdir(parents=True, exist_ok=True)
                
                tile_path = tile_dir / f"{y}.png"
                tile.save(tile_path, 'PNG')
                created_count += 1
    
    print(f"✅ Created {created_count} tiles at zoom level {zoom} (max grid: {tiles_at_zoom}x{tiles_at_zoom})")


def build_pyramid(parcels: Dict[Tuple[int, int], Image.Image], output_dir: Path):
    """Build complete tile pyramid from zoom 6 down to zoom 0."""
    print(f"\n📦 Building tile pyramid in {output_dir.absolute()}")
    print(f"   Zoom levels: {MIN_ZOOM} to {MAX_ZOOM}")
    print(f"   Tile size: {TILE_SIZE}x{TILE_SIZE} pixels")
    print()
    
    # Create zoom level 6 (1:1 with parcels)
    print(f"🔨 Zoom level {MAX_ZOOM} (1:1 with parcels, no scaling)...")
    create_zoom_6_tiles(parcels, output_dir)
    print()
    
    # Create zoom levels 5 down to 0 (with scaling)
    for zoom in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        scale_factor = 2 ** (MAX_ZOOM - zoom)
        print(f"🔨 Zoom level {zoom} (scale {scale_factor}x from parcels)...")
        create_zoom_level(zoom, output_dir)
        print()
    
    print("✅ Tile pyramid complete!")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build tile pyramid from parcel images'
    )
    parser.add_argument(
        '--parcels-dir',
        default='parcels',
        help='Directory containing parcel PNG files (default: parcels)'
    )
    parser.add_argument(
        '--output-dir',
        default='docs/world',
        help='Output directory for tile pyramid (default: docs/world)'
    )
    
    args = parser.parse_args()
    
    parcels_dir = Path(args.parcels_dir)
    output_dir = Path(args.output_dir)
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  World Tile Pyramid Builder                               ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"Parcels dir:  {parcels_dir.absolute()}")
    print(f"Output dir:   {output_dir.absolute()}")
    print()
    
    # Load parcel images
    print("📂 Loading parcel images...")
    parcels = load_parcels(parcels_dir)
    
    if not parcels:
        print("❌ No parcel images found!")
        return 1
    
    print(f"\n✅ Loaded {len(parcels)} parcels")
    print()
    
    # Build pyramid
    output_dir.mkdir(parents=True, exist_ok=True)
    build_pyramid(parcels, output_dir)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
