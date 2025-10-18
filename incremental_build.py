#!/usr/bin/env python3
"""
Incremental World Tile Builder

Uses file timestamps to rebuild only out-of-date tiles in the pyramid.
Works like a traditional build system (make/ninja):
- Rebuild zoom 6 tiles when parcel files are newer
- Rebuild parent tiles when any child tile is newer
- Compress changed tiles with lossless PNG optimization

Usage:
  python incremental_build.py [--parcels-dir parcels] [--output-dir docs/world] [--init] [--no-compress]
"""

import argparse
import math
import shutil
import sys
from pathlib import Path
from typing import Optional, List

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
LABEL_MAX_DISTANCE = 19  # Maximum Euclidean distance from center in parcels for label generation

def get_grid_size_at_zoom(zoom: int) -> int:
    """Get the number of tiles in each dimension at a given zoom level."""
    return 2 ** zoom

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


def parcel_name(row: int, col: int) -> str:
    """Generate a parcel label from row and column indices.
    
    Args:
        row: 0-based row index (0=A, 37=AL)
        col: 0-based col index (0=column 1, 37=column 38)
        
    Returns:
        Parcel label string (e.g., "A1", "B12", "AL38")
    """
    return f"{letter_of_index(row)}{col + 1}"


def maxzoom_tile_coords_to_parcel_coords(x: int, y: int) -> Optional[tuple[int, int]]:
    """Convert tile coordinates to parcel grid coordinates.
    
    Handles the offset calculation to map from the 64x64 tile grid at MAX_ZOOM
    to the centered 38x38 parcel grid.
    
    Args:
        x: Tile x coordinate at MAX_ZOOM
        y: Tile y coordinate at MAX_ZOOM
        
    Returns:
        (row, col) tuple if within grid bounds, None otherwise
    """
    # Calculate offset inline: center the 38x38 parcel grid in the 64x64 tile grid
    offset = (get_grid_size_at_zoom(MAX_ZOOM) - GRID_SIZE) // 2
    
    # Convert tile coordinates to parcel grid coordinates
    col = x - offset
    row = offset + (GRID_SIZE - 1) - y
    
    # Check bounds
    if row < 0 or row >= GRID_SIZE or col < 0 or col >= GRID_SIZE:
        return None
    
    return (row, col)



# only called durring label gneration so dont sweat it
def is_parcel_claimable_maxzoom_coords(x: int, y: int) -> Optional[str]:
    """Check if a tile position at MAX_ZOOM corresponds to a claimable parcel.
    
    Takes tile coordinates and checks if the parcel is within the claimable
    distance from center (within bounds and within LABEL_MAX_DISTANCE).
    
    Args:
        x: Tile x coordinate at MAX_ZOOM
        y: Tile y coordinate at MAX_ZOOM
        
    Returns:
        Parcel label string if claimable, None otherwise
    """
    # Convert to parcel grid coordinates
    coords = maxzoom_tile_coords_to_parcel_coords(x, y)
    if coords is None:
        return None
    
    row, col = coords
    
    # Calculate center of the 38x38 grid (0-based indexing)
    center_row = (GRID_SIZE - 1) / 2  # 18.5
    center_col = (GRID_SIZE - 1) / 2  # 18.5
    
    # Calculate Euclidean distance from center
    distance = math.sqrt((row - center_row) ** 2 + (col - center_col) ** 2)
    
    # Skip tiles that are too far from center (not claimable)
    if distance > LABEL_MAX_DISTANCE:
        return None

    # Generate and return the parcel label
    return parcel_name(row, col)

def get_placeholder_tile_path(output_dir: Path) -> Path:
    """Get path to the placeholder tile file."""
    return output_dir / "placeholder_tile.png"

def generate_placeholder_tile_file(output_dir: Path) -> None:
    """Generate a TILE_SIZE x TILE_SIZE transparent PNG tile."""
    placeholder_path = get_placeholder_tile_path(output_dir)
    placeholder_path.parent.mkdir(parents=True, exist_ok=True)

    # from gemini 2.5    
    # --- Create a 1-bit TILE_SIZE x TILE_SIZE   image ---
    # Mode '1' is a 1-bit, black-and-white image.
    # We initialize the background color to 1 (which corresponds to white).
    img = Image.new('RGBA', (1, 1), (255, 255,255, 0))  # white

    # --- Save the image as PNG ---
    # By setting 'transparency=1', we tell the PNG saver to
    # make the color '1' (white) fully transparent.
    # The color '0' (black) will remain opaque.
    img.save(placeholder_path, 'PNG' ,optimize=True)    


def maxzoom_tile_coords_to_label(x: int, y: int) -> Optional[str]:
    """Convert 0-based tile x,y coords into a parcel label taking into account the offset.
    
    Returns the label if the coords are within the grid bounds, else None.
    Does not check distance from center - use is_parcel_claimable_maxzoom_coords for that.
    """
    # Convert to parcel grid coordinates
    coords = maxzoom_tile_coords_to_parcel_coords(x, y)
    if coords is None:
        return None
    
    row, col = coords
    return parcel_name(row, col)    


def create_label_tile_maxzoom(label: str) -> Image.Image:
    """Create a transparent tile with parcel label and grid lines at MAX_ZOOM.
    
    Args:
        label: Parcel label string (e.g., "A1", "B12", "AL38")
    
    Returns:
        PIL Image with transparent background, green grid lines, and blue label text
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
    
    # Calculate font size: 25% of tile size
    # remember that the longest label is AL38 which is 4 letters long
    font_size = int(TILE_SIZE * 0.25)
    
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
    
    # Draw text centered (blue, full opacity - opacity will be controlled by layer)
    text_color = (0, 0, 255, 255)  # rgba(0, 0, 255, 1.0) -> full opacity
    
    # Use anchor='mm' (middle-middle) to center both horizontally and vertically
    center_x = TILE_SIZE / 2
    center_y = TILE_SIZE / 2
    
    draw.text((center_x, center_y), label, fill=text_color, font=font, anchor='mm')
    
    return img


def create_tile_from_children(zoom: int, x: int, y: int, zoom_dir: Path) -> Image.Image:
    """Create a tile by combining and scaling 4 child tiles from zoom+1.
    
    Returns:
        PIL Image
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
            if not child_path.exists():
                raise Exception(f"Child tile {child_path} does not exist")

            # Open and convert to RGBA to preserve transparency
            child_img = Image.open(child_path)
            
            # For 1-bit images with transparency, we need to handle it specially
            if child_img.mode == '1' and 'transparency' in child_img.info:
                # Convert to grayscale first to get the pixel values
                gray = child_img.convert('L')
                # Create RGBA with alpha channel based on white pixels
                child_rgba = Image.new('RGBA', child_img.size)
                pixels = child_rgba.load()
                gray_pixels = gray.load()
                for py in range(child_img.height):
                    for px in range(child_img.width):
                        if gray_pixels[px, py] == 255:  # White pixel
                            pixels[px, py] = (255, 255, 255, 0)  # Transparent
                        else:  # Black pixel
                            pixels[px, py] = (0, 0, 0, 255)  # Opaque black
            else:
                # For other formats, just convert to RGBA
                child_rgba = child_img.convert('RGBA')
            
            row.append(child_rgba)
        
        child_tiles.append(row)
    
    # # Check if all children are empty (transparent)
    # all_empty = all(
    #     img.getbbox() is None 
    #     for row in child_tiles 
    #     for img in row
    # )
    # if all_empty:
    #     return None
    
    # TODO: MAYBE HERE WE COULD CHECK IF THE 4 child tiles are placeholders and then use the placeholder for this tile too maybe it will be smaller?

    # Combine 4 tiles into one 1000x1000 image
    combined = Image.new('RGBA', (TILE_SIZE * 2, TILE_SIZE * 2), (0, 0, 0, 0))
    for dy in range(2):
        for dx in range(2):
            # Pass the image as mask to preserve alpha channel transparency
            combined.paste(child_tiles[dy][dx], (dx * TILE_SIZE, dy * TILE_SIZE), child_tiles[dy][dx])
    
    # Scale down to TILE_SIZE x TILE_SIZE using high-quality resampling (anti-aliasing)
    # LANCZOS properly handles alpha channel in RGBA mode
    scaled = combined.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.LANCZOS)
    
    # Ensure we're returning RGBA mode
    if scaled.mode != 'RGBA':
        scaled = scaled.convert('RGBA')
            
    return scaled


def get_mtime(filepath: Path) -> float:
    """Get modification time of a file, or 0 if it doesn't exist."""
    try:
        return filepath.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def is_file_newer_than(source_path: Path, destination_path: Path) -> bool:
    source_mtime = get_mtime(source_path)
    destination_mtime = get_mtime(destination_path)
    
    return source_mtime > destination_mtime

BG_COLOR = ( 0 , 0 , 255)

def convert_parcel_to_tile(input_path, output_path):
    """Convert parcel image to 1-bit black/white with white as transparent.
    
    Note: Does not optimize here - compression happens in separate pass.
    """
    # Open and load the image
    img = Image.open(input_path)
    
    # Convert to grayscale first (luminance-based)
    img_gray = img.convert('L')
    
    # Convert to 1-bit using 50% threshold: >127 becomes white (1), <=127 becomes black (0)
    img_1bit = img_gray.convert('1')
    
    # Save as PNG with white (color value 1) set to transparent
    # Don't optimize here - we'll do compression in a separate pass
    img_1bit.save(output_path, 'PNG', transparency=1)
    

def compress_png(png_path: Path) -> None:
    """Compress a PNG file losslessly using PIL optimization.
    
    Args:
        png_path: Path to PNG file to compress
    """
    # Load the image
    img = Image.open(png_path)
    
    # Save with maximum compression
    # optimize=True enables PIL's PNG optimizer
    # compress_level=9 uses maximum zlib compression
    img.save(png_path, 'PNG', optimize=True, compress_level=9)


def incremental_update_image_tile_at_maxzoom(x: int, y: int, parcels_dir: Path, output_dir: Path) -> Optional[Path]:
    """Rebuild a single image tile at MAX_ZOOM if needed. Returns tile path if rebuilt.
    
    Checks if parcel exists for the tile position. If not, uses transparent pixel.
    If parcel exists, checks if it's newer than the tile and rebuilds if needed.
    
    Args:
        x: Tile x coordinate at MAX_ZOOM
        y: Tile y coordinate at MAX_ZOOM
        parcels_dir: Path to directory containing parcel PNG files
        output_dir: Root output directory
        
    Returns:
        Path to tile if rebuilt, None if skipped (up to date)
    """
    # Get parcel label for this tile position (accounts for offset)
    parcel_name = maxzoom_tile_coords_to_label(x, y)

    image_tile_path = output_dir / "images" / str(MAX_ZOOM) / str(x) / f"{y}.png"

    # lets special case out the cases where we do not just load the parcel into the tile

    # do we need a placeholder?
    # yes if the parcel is not in the grid or there is no parcel file


    # we need to generate the tile if there is no current tile file OR the parcel is newer than the tile
    # if there is no parcel file, then it can not be newer (at least until we start delaing with deletes)

    parcel_exists = False
    
    if parcel_name is not None:
        parcel_path = parcels_dir / f"{parcel_name}.png"
        parcel_exists = parcel_path.exists()
        
    if image_tile_path.exists():
        if not parcel_exists:
            # we already generated a placeholder for this tile
            return None

        if not is_file_newer_than(parcel_path, image_tile_path):
            # tile is up to date
            return None


    # we need to generate the tile

    if not parcel_exists:
        # tile gets a placeholder
        placeholder_path = get_placeholder_tile_path(output_dir)
        image_tile_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(placeholder_path, image_tile_path)
        return image_tile_path

    # just a normal parcel to a tile
    convert_parcel_to_tile(parcel_path, image_tile_path)
    return image_tile_path


def incrementral_update_all_image_tiles_as_maxzoom(parcels_dir: Path, output_dir: Path, changed_tiles: List[Path]):
    """Scan all tiles at MAX_ZOOM and rebuild those that are out of date.
    
    Iterates through all 64x64 tiles at zoom 6 (MAX_ZOOM). For each tile,
    calls incremental_update_image_tile_at_maxzoom to check if rebuild is needed
    and tracks total tiles processed and how many were rebuilt.
    
    Args:
        parcels_dir: Path to directory containing parcel PNG files
        output_dir: Root output directory
        changed_tiles: List to append changed tile paths to
    """
    rebuilt_count = 0
    skipped_count = 0   
    
    tiles_at_maxzoom = get_grid_size_at_zoom(MAX_ZOOM)  # 64x64 tiles at zoom 6
    
    for x in range(tiles_at_maxzoom):
        for y in range(tiles_at_maxzoom):
            tile_path = incremental_update_image_tile_at_maxzoom(x, y, parcels_dir, output_dir)
            if tile_path:
                changed_tiles.append(tile_path)
                rebuilt_count += 1
            else:
                skipped_count += 1
    
    total_processed = rebuilt_count + skipped_count
    print(f"   Processed: {total_processed}, Rebuilt: {rebuilt_count}, Up-to-date: {skipped_count}")
    
    

def rebuild_tile_at_zoom(zoom: int, x: int, y: int, layer_root: Path):
    """Rebuild a single tile at given zoom level by combining children.
    
    Always creates a tile (even if transparent) to ensure all tiles exist at all zoom levels.
    This prevents 404 errors that would be cached by Leaflet.
    
    Args:
        zoom: Zoom level to rebuild
        x: Tile x coordinate
        y: Tile y coordinate
        layer_root: Root path of the layer (e.g., output_dir / "images" or output_dir / "labels")
    """
    zoom_dir = layer_root / str(zoom)
    tile = create_tile_from_children(zoom, x, y, zoom_dir)
    
    tile_dir = zoom_dir / str(x)
    tile_dir.mkdir(parents=True, exist_ok=True)
    tile_path = tile_dir / f"{y}.png"
    # Save with explicit RGBA mode to preserve transparency
    # Don't optimize here - we'll do compression in a separate pass
    tile.save(tile_path, 'PNG')

def incremental_update_tile_at_zoom(zoom: int, x: int, y: int, layer_root: Path, changed_tiles: List[Path] = None) -> bool:
    """Rebuild a tile at given zoom level only if any child tile is newer.
    
    Checks timestamps of all 4 child tiles and rebuilds parent tile only if
    at least one child is newer than the parent.
    
    Args:
        zoom: Zoom level to rebuild
        x: Tile x coordinate
        y: Tile y coordinate
        layer_root: Root path of the layer (e.g., output_dir / "images" or output_dir / "labels")
        changed_tiles: Optional list to append changed tile paths to
        
    Returns:
        True if tile was rebuilt, False if skipped (up to date)
    """
    # Get parent tile path
    parent_path = layer_root / str(zoom) / str(x) / f"{y}.png"
    parent_mtime = get_mtime(parent_path)
    
    # Check all 4 child tiles
    child_zoom = zoom + 1
    needs_rebuild = False
    
    for dy in range(2):
        for dx in range(2):
            child_x = x * 2 + dx
            child_y = y * 2 + dy
            child_path = layer_root / str(child_zoom) / str(child_x) / f"{child_y}.png"
            
            child_mtime = get_mtime(child_path)
            if child_mtime > parent_mtime:
                needs_rebuild = True
                break
        if needs_rebuild:
            break
    
    if needs_rebuild:
        # print(f"🔨 Rebuilding tile {zoom}/{x}/{y}")
        rebuild_tile_at_zoom(zoom, x, y, layer_root)
        if changed_tiles is not None:
            changed_tiles.append(parent_path)
        return True
    
    return False

def incremental_update_all_tiles_at_zoom(zoom: int, layer_root: Path, changed_tiles: List[Path] = None):
    """Incrementally update all tiles at given zoom level by checking child timestamps.
    
    Args:
        zoom: Zoom level to rebuild
        layer_root: Root path of the layer (e.g., output_dir / "images" or output_dir / "labels")
        changed_tiles: Optional list to append changed tile paths to
    """
    tiles_at_zoom = get_grid_size_at_zoom(zoom)
    rebuilt_count = 0
    skipped_count = 0
    
    for x in range(tiles_at_zoom):
        for y in range(tiles_at_zoom):
            if incremental_update_tile_at_zoom(zoom, x, y, layer_root, changed_tiles):
                rebuilt_count += 1
            else:
                skipped_count += 1
    
    total_processed = rebuilt_count + skipped_count
    print(f"   Processed: {total_processed}, Rebuilt: {rebuilt_count}, Up-to-date: {skipped_count}")


def rebuild_all_tiles_at_zoom(zoom: int, layer_root: Path): 
    """Rebuild all tiles at given zoom level by combining children.
    
    Args:
        zoom: Zoom level to rebuild
        layer_root: Root path of the layer (e.g., output_dir / "images" or output_dir / "labels")
    """  
    tiles_at_zoom = get_grid_size_at_zoom(zoom)
    created_count = 0
    
    for x in range(tiles_at_zoom):
        for y in range(tiles_at_zoom):
            rebuild_tile_at_zoom(zoom, x, y, layer_root)
            created_count += 1

    print(f"   Created {created_count} tiles at zoom level {zoom}")


def incremental_update_tiles_at_all_zooms(layer_root: Path, changed_tiles: List[Path] = None):
    """Incrementally update tiles at all zoom levels from MAX_ZOOM-1 down to MIN_ZOOM.
    
    Only rebuilds tiles whose children have changed (timestamp-based).
    Assumes tiles at max zoom are built and valid.
    
    Args:
        layer_root: Root path of the layer (e.g., output_dir / "images" or output_dir / "labels")
        changed_tiles: Optional list to append changed tile paths to
    """
    for zoom in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        print(f"🔨 Zoom level {zoom}...")
        incremental_update_all_tiles_at_zoom(zoom, layer_root, changed_tiles)


def rebuild_tiles_at_all_zooms(layer_root: Path):
    """Rebuild tiles at all zoom levels from MAX_ZOOM-1 down to MIN_ZOOM.
    
    Unconditionally rebuilds all tiles (used for --init).
    Assumes tiles at max zoom are built and valid.
    
    Args:
        layer_root: Root path of the layer (e.g., output_dir / "images" or output_dir / "labels")
    """
    for zoom in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        print(f"🔨 Zoom level {zoom}...")
        rebuild_all_tiles_at_zoom(zoom, layer_root)

def generate_labels_maxzoom(output_dir: Path):
    """Generate labels for zoom level MAX_ZOOM.
    
    Iterates through all 64x64 tiles at zoom 6. For each tile:
    - If it corresponds to a claimable parcel position, create label tile
    - Otherwise, create transparent pixel tile
    """
    tiles_at_maxzoom = get_grid_size_at_zoom(MAX_ZOOM)  # 64   
    labels_created = 0
    transparent_created = 0
    
    for x in range(tiles_at_maxzoom):
        for y in range(tiles_at_maxzoom):
            label_dir = output_dir / "labels" / str(MAX_ZOOM) / str(x)
            label_dir.mkdir(parents=True, exist_ok=True)
            label_path = label_dir / f"{y}.png"
            
            # Check if this position is claimable and get label
            parcel_name = is_parcel_claimable_maxzoom_coords(x, y)
            if parcel_name:
                # Create label tile with text and grid for claimable parcel
                label_img = create_label_tile_maxzoom(parcel_name)
                label_img.save(label_path, 'PNG', optimize=True)
                labels_created += 1
            else:
                # Copy placeholder tile file for non-claimable positions
                placeholder_path = get_placeholder_tile_path(output_dir)
                shutil.copy(placeholder_path, label_path)
                transparent_created += 1
    
    print(f"   Created {labels_created} label tiles and {transparent_created} transparent tiles")


def init_output_dir(output_dir: Path):
    """Initialize output directory, clearing all existing tiles and rebuilding from scratch."""


    print("🔨 Purging output directory...")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # we will use this to fill in any MAXZOOM tile that does not have a proper source,
    # so either an image tile that no parcel exists for, or a label tile for non-claimable parcels
    print("🔨 Generating placeholder tile file...")
    generate_placeholder_tile_file(output_dir)
    
    # note that we do not need to explicitly rebuild the labels tree here since we deleted the output dir so all
    # the labels will anturally get rebuilt
    
    print("🏷️  Building labels tree...")
    print()
    generate_labels_maxzoom(output_dir)
    labels_root = output_dir / "labels"

    # this works becuase we purged the directory above so all tiles will be rebuilt
    incremental_update_tiles_at_all_zooms(labels_root)
    print()
    print("✅ Labels tree complete")
    print()

def compress_changed_tiles(changed_tiles: List[Path]):
    """Compress all changed PNG tiles.
    
    Args:
        changed_tiles: List of PNG file paths to compress
    """
    if not changed_tiles:
        print("   No tiles to compress")
        return
    
    compressed_count = 0
    total_saved = 0
    
    for tile_path in changed_tiles:
        if not tile_path.exists():
            continue
            
        original_size = tile_path.stat().st_size
        compress_png(tile_path)
        new_size = tile_path.stat().st_size
        saved = original_size - new_size
        total_saved += saved
        compressed_count += 1
    
    total_saved_kb = total_saved / 1024
    print(f"   Compressed {compressed_count} tiles, saved {total_saved_kb:.1f} KB")


def incremental_build(parcels_dir: Path, output_dir: Path, compress: bool = True):
    """Perform timestamp-based incremental build of world tiles.
    
    Args:
        parcels_dir: Path to directory containing parcel PNG files
        output_dir: Root output directory
        compress: If True, compress changed tiles after building
    """
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Incremental World Tile Builder (Timestamp-based)          ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
        
    # test if output dir exists, if not tell user to run --init    
    if not output_dir.exists():
        print("❌ Output directory does not exist. Please run --init first.")
        sys.exit(1)
    
    # Track all changed tiles for compression
    changed_tiles = []
    
    # Phase 1: Build maxzoom images (check all tile positions)
    print(f"🔨 Phase 1: Zoom level {MAX_ZOOM} ...")
    incrementral_update_all_image_tiles_as_maxzoom(parcels_dir, output_dir, changed_tiles)
    print()
    
    # Phase 2: Build zoom levels 5 down to 0 (check child timestamps)
    images_root = output_dir / "images"
    incremental_update_tiles_at_all_zooms(images_root, changed_tiles)
    print()
    
    # Phase 3: Compress changed tiles
    if compress and changed_tiles:
        print(f"🗜️  Phase 3: Compressing {len(changed_tiles)} changed tiles...")
        compress_changed_tiles(changed_tiles)
        print()
    
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Incrementally build tile pyramid using timestamp-based dependencies'
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
    parser.add_argument(
        '--init',
        action='store_true',
        help='Initialize output directory, clearing all existing tiles and rebuilding from scratch'
    )
    parser.add_argument(
        '--no-compress',
        action='store_true',
        help='Skip PNG compression after building tiles'
    )
    
    args = parser.parse_args()
    
    parcels_dir = Path(args.parcels_dir)
    output_dir = Path(args.output_dir)
    
    if args.init:
        init_output_dir(output_dir)
    
    # Determine if compression should be enabled
    compress = not args.no_compress
    
    return incremental_build(parcels_dir, output_dir, compress)


if __name__ == '__main__':
    sys.exit(main())
