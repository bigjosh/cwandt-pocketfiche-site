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
import shutil
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
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
LABEL_MAX_DISTANCE = 19  # Maximum Euclidean distance from center for label generation

# Matches filenames like: tile-H4.png, tile-AA12.png, tile-R17.png
FILENAME_RE = re.compile(r"^tile-([A-Za-z]+)(\d+)\.png$", re.IGNORECASE)


def index_of_letter(letters: str) -> int:
    """Convert Excel-style letters to 0-based row index.
    A->0, B->1, ..., Z->25, AA->26, AB->27, ..., AL->37
    """
    result = 0
    for char in letters.upper():
        result = (result * 26) + (ord(char) - ord('A') + 1)
    return result - 1


def letter_of_index(idx: int) -> str:
    """Convert 0-based index to Excel-style letters.
    0->A, 1->B, ..., 25->Z, 26->AA, 27->AB, ..., 37->AL
    """
    idx += 1  # Convert to 1-based
    result = ''
    while idx > 0:
        idx -= 1
        result = chr(ord('A') + (idx % 26)) + result
        idx //= 26
    return result

def parse_parcel_filename(filename: str) -> Optional[Tuple[int, int]]:
    """Parse parcel filename to extract zero based (row, col) coordinates.
    
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
    
    # retruns 0 based row 
    row_letters = m.group(1).upper()
    try:
        col = int(m.group(2))-1
    except ValueError:
        return None
    
    row = index_of_letter(row_letters)
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


def create_label_tile(row: int, col: int, zoom: int = MAX_ZOOM) -> Image.Image:
    """Create a transparent tile with parcel label and grid lines.
    
    At zoom 6: Shows text label and grid border
    At lower zooms: Shows only grid border (text would be too small)
    
    Args:
        row: 0-based row index (0=A, 37=AL)
        col: 0-based col index (0=1, 37=38)
        zoom: Zoom level (affects whether text is shown)
    
    Returns:
        PIL Image with transparent background, green grid lines, and red label text
    """
    # Create transparent image
    img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw grid border (green, semi-transparent)
    grid_color = (19, 211, 61, 128)  # rgba(19, 211, 61, 0.5)
    border_width = 1
    draw.rectangle(
        [(0, 0), (TILE_SIZE - 1, TILE_SIZE - 1)],
        outline=grid_color,
        width=border_width
    )
    
    # Only draw text at zoom levels where it's legible
    # At zoom 6, text is 250px (50% of 500px tile)
    # At zoom 2, text would be ~16px (legible)
    # Below zoom 2, skip text
    MIN_TEXT_ZOOM = 2
    
    if zoom >= MIN_TEXT_ZOOM:
        # Generate parcel label (e.g., "A1", "B12", "AL38")
        label = f"{letter_of_index(row)}{col + 1}"
        
        # Calculate font size: 50% of tile size
        font_size = int(TILE_SIZE * 0.5)
        
        # Try to load a bold font, fall back to default
        try:
            # Try Impact font (thick and blocky, like in CSS)
            font = ImageFont.truetype("impact.ttf", font_size)
        except:
            try:
                # Fall back to Arial Bold
                font = ImageFont.truetype("arialbd.ttf", font_size)
            except:
                # Use default font with larger size
                font = ImageFont.load_default()
        
        # Draw text centered (red, full opacity - opacity will be controlled by layer)
        text_color = (255, 0, 0, 255)  # rgba(255, 0, 0, 1.0) -> full opacity
        
        # Use anchor='mm' (middle-middle) to center both horizontally and vertically
        center_x = TILE_SIZE / 2
        center_y = TILE_SIZE / 2
        
        draw.text((center_x, center_y), label, fill=text_color, font=font, anchor='mm')
    
    return img

# not working...
# u0 -> a21    



def create_zoom_6_tiles(parcels: Dict[Tuple[int, int], Image.Image], output_dir: Path):
    """Create zoom level 6 tiles (1:1 with parcels, no scaling).
    
    At zoom 6 in standard slippy map: 64x64 tiles (2^6 = 64)
    Our 38x38 parcel world is centered within this grid.
    - Offset of 13 on each side: (64-38)/2 = 13
    - A1 (row=0, col=0) at bottom-left maps to tile (13, 50)
    - AL38 (row=37, col=37) at top-right maps to tile (50, 13)
    - Y-axis is inverted: row=0 (bottom) → high y, row=37 (top) → low y
    """
    zoom_dir = output_dir / "images" / "6"
    
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
    
    print(f"✅ Created {len(parcels)} image tiles at zoom level 6")


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


def create_tile_from_children(zoom: int, x: int, y: int, zoom_dir: Path) -> Optional[Image.Image]:
    """Create a tile by combining and scaling 4 child tiles from zoom+1.
    
    Returns:
        PIL Image if tile was created, None if no child tiles exist
    """
    child_zoom = zoom + 1
    child_zoom_dir = zoom_dir.parent / str(child_zoom)
    
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


def create_zoom_level(zoom: int, zoom_dir: Path):
    """Create all tiles for a given zoom level by scaling from zoom+1.
    
    Standard slippy map: at zoom Z, there are 2^Z tiles per side.
    We only create tiles that have content (where parcels exist).
    """
    tiles_at_zoom = 2 ** zoom
    
    created_count = 0
    for x in range(tiles_at_zoom):
        for y in range(tiles_at_zoom):
            tile = create_tile_from_children(zoom, x, y, zoom_dir)
            if tile is not None:
                tile_dir = zoom_dir / str(x)
                tile_dir.mkdir(parents=True, exist_ok=True)
                
                tile_path = tile_dir / f"{y}.png"
                tile.save(tile_path, 'PNG')
                created_count += 1
    
    print(f"✅ Created {created_count} tiles at zoom level {zoom} (max grid: {tiles_at_zoom}x{tiles_at_zoom})")


def create_label_zoom_6_tiles(output_dir: Path):
    """Create zoom level 6 label tiles for all 38x38 parcels.
    
    Each tile contains the parcel name and grid border.
    Only generates labels for parcels within 19 units Euclidean distance from center.
    """
    zoom_dir = output_dir / "labels" / "6"
    
    # Calculate center of the 38x38 grid (0-based indexing)
    center_row = (GRID_SIZE - 1) / 2  # 18.5
    center_col = (GRID_SIZE - 1) / 2  # 18.5
    
    count = 0
    skipped = 0
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            # Calculate Euclidean distance from center
            distance = math.sqrt((row - center_row) ** 2 + (col - center_col) ** 2)
            
            # Skip tiles that are too far from center
            if distance > LABEL_MAX_DISTANCE:
                skipped += 1
                continue
            
            # Create label tile
            label_img = create_label_tile(row, col, zoom=MAX_ZOOM)
            
            # Calculate tile position (same as parcel tiles)
            tile_x = col + OFFSET
            tile_y = OFFSET + (GRID_SIZE - 1) - row
            
            tile_dir = zoom_dir / str(tile_x)
            tile_dir.mkdir(parents=True, exist_ok=True)
            
            tile_path = tile_dir / f"{tile_y}.png"
            label_img.save(tile_path, 'PNG')
            count += 1
    
    print(f"✅ Created {count} label tiles at zoom level 6 (skipped {skipped} far parcels)")




def build_label_pyramid(output_dir: Path):
    """Build complete label tile pyramid from zoom 6 down to zoom 0."""
    print(f"\n🏷️  Building label tile pyramid")
    print(f"   Zoom levels: {MIN_ZOOM} to {MAX_ZOOM}")
    print(f"   Tile size: {TILE_SIZE}x{TILE_SIZE} pixels")
    print()
    
    # Create zoom level 6 labels (1:1 with parcels, includes text)
    print(f"🔨 Zoom level {MAX_ZOOM} (with text labels)...")
    create_label_zoom_6_tiles(output_dir)
    print()
    
    # Create zoom levels 5 down to 0 (with scaling)
    # Text will automatically disappear at zoom < 2 due to scaling
    labels_dir = output_dir / "labels"
    for zoom in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        scale_factor = 2 ** (MAX_ZOOM - zoom)
        print(f"🔨 Zoom level {zoom} (scale {scale_factor}x)...")
        zoom_dir = labels_dir / str(zoom)
        create_zoom_level(zoom, zoom_dir)
        print()
    
    print("✅ Label tile pyramid complete!")


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
    images_dir = output_dir / "images"
    for zoom in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        scale_factor = 2 ** (MAX_ZOOM - zoom)
        print(f"🔨 Zoom level {zoom} (scale {scale_factor}x from parcels)...")
        zoom_dir = images_dir / str(zoom)
        create_zoom_level(zoom, zoom_dir)
        print()
    
    print("✅ Image tile pyramid complete!")


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
    
    # Clean output directory
    if output_dir.exists():
        print(f"🧹 Cleaning old files from {output_dir.absolute()}...")
        shutil.rmtree(output_dir)
        print("✅ Old files removed")
        print()
    
    # Build tile pyramids (both images and labels under same root)
    output_dir.mkdir(parents=True, exist_ok=True)
    build_pyramid(parcels, output_dir)
    build_label_pyramid(output_dir)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
