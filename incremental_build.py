#!/usr/bin/env python3
"""
Incremental World Tile Builder

Uses file timestamps to rebuild only out-of-date tiles in the pyramid.
Works like a traditional build system (make/ninja):
- Rebuild zoom 6 tiles when parcel files are newer
- Rebuild parent tiles when any child tile is newer

Usage:
  python incremental_build.py [--parcels-dir parcels] [--output-dir docs/world] [--force]
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Set, Tuple, Optional
import shutil

# Import the original build_world functions
from build_world import (
    TILE_SIZE, MAX_ZOOM, MIN_ZOOM, GRID_SIZE, OFFSET,
    parse_parcel_filename, snap_to_black_or_white, create_label_tile,
    create_tile_from_children, index_of_letter, letter_of_index
)

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow library required. Install with: pip install Pillow")
    sys.exit(1)


def get_mtime(filepath: Path) -> float:
    """Get modification time of a file, or 0 if it doesn't exist."""
    try:
        return filepath.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def is_tile_out_of_date_zoom_6(parcel_path: Path, tile_path: Path) -> bool:
    """Check if zoom 6 tile needs rebuilding based on parcel timestamp."""
    parcel_mtime = get_mtime(parcel_path)
    tile_mtime = get_mtime(tile_path)
    
    # Rebuild if tile doesn't exist or parcel is newer
    return tile_mtime == 0.0 or parcel_mtime > tile_mtime


def get_child_tile_paths(zoom: int, x: int, y: int, output_dir: Path, layer: str) -> list:
    """Get paths to the 4 child tiles for a given parent tile."""
    child_zoom = zoom + 1
    child_zoom_dir = output_dir / layer / str(child_zoom)
    
    paths = []
    for dy in range(2):
        for dx in range(2):
            child_x = x * 2 + dx
            child_y = y * 2 + dy
            paths.append(child_zoom_dir / str(child_x) / f"{child_y}.png")
    
    return paths


def is_tile_out_of_date(zoom: int, x: int, y: int, output_dir: Path, layer: str) -> bool:
    """Check if tile needs rebuilding based on child tile timestamps."""
    tile_path = output_dir / layer / str(zoom) / str(x) / f"{y}.png"
    tile_mtime = get_mtime(tile_path)
    
    # If tile doesn't exist, check if any children exist
    if tile_mtime == 0.0:
        child_paths = get_child_tile_paths(zoom, x, y, output_dir, layer)
        # Rebuild if any child exists
        return any(get_mtime(p) > 0.0 for p in child_paths)
    
    # Tile exists, check if any child is newer
    child_paths = get_child_tile_paths(zoom, x, y, output_dir, layer)
    max_child_mtime = max(get_mtime(p) for p in child_paths)
    
    return max_child_mtime > tile_mtime


def create_transparent_tile() -> Image.Image:
    """Create a 1x1 transparent pixel image."""
    return Image.new('RGBA', (1, 1), (0, 0, 0, 0))


def load_parcel_or_transparent(filepath: Optional[Path]) -> Image.Image:
    """Load and process a parcel image, or return transparent pixel if missing.
    
    Args:
        filepath: Path to parcel file, or None for missing parcel
        
    Returns:
        PIL Image (either loaded parcel or 1x1 transparent pixel)
    """
    if filepath is None or not filepath.exists():
        # Missing parcel - return transparent pixel
        return create_transparent_tile()
    
    try:
        img = Image.open(filepath)
        if img.size != (TILE_SIZE, TILE_SIZE):
            print(f"⚠️  Warning: {filepath.name} is {img.size}, expected {TILE_SIZE}x{TILE_SIZE}")
        img = img.convert('RGBA')
        img = snap_to_black_or_white(img)
        return img
    except Exception as e:
        print(f"❌ Failed to load {filepath.name}: {e}, using transparent pixel")
        return create_transparent_tile()


def rebuild_tile_at_zoom_6(row: int, col: int, parcel_img: Image.Image, output_dir: Path, is_empty: bool = False) -> Tuple[Path, Path]:
    """Rebuild a single tile at zoom level 6. Returns paths to created tiles.
    
    Args:
        row: Grid row position
        col: Grid column position
        parcel_img: Parcel image (or transparent pixel if empty)
        output_dir: Output directory
        is_empty: True if this is an empty/missing parcel location
    """
    tile_x = col + OFFSET
    tile_y = OFFSET + (GRID_SIZE - 1) - row
    
    # Save image tile
    image_dir = output_dir / "images" / "6" / str(tile_x)
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"{tile_y}.png"
    parcel_img.save(image_path, 'PNG')
    
    # Save label tile
    label_img = create_label_tile(row, col, zoom=MAX_ZOOM)
    label_dir = output_dir / "labels" / "6" / str(tile_x)
    label_dir.mkdir(parents=True, exist_ok=True)
    label_path = label_dir / f"{tile_y}.png"
    label_img.save(label_path, 'PNG')
    
    return image_path, label_path


def rebuild_tile_at_zoom(zoom: int, x: int, y: int, output_dir: Path, layer: str) -> bool:
    """Rebuild a single tile at given zoom level by combining children."""
    zoom_dir = output_dir / layer / str(zoom)
    tile = create_tile_from_children(zoom, x, y, zoom_dir)
    
    if tile is not None:
        tile_dir = zoom_dir / str(x)
        tile_dir.mkdir(parents=True, exist_ok=True)
        tile_path = tile_dir / f"{y}.png"
        tile.save(tile_path, 'PNG')
        return True
    return False


def get_all_tile_coords_at_zoom(zoom: int) -> Set[Tuple[int, int]]:
    """Get all possible tile coordinates at a given zoom level."""
    tiles_at_zoom = 2 ** zoom
    coords = set()
    for x in range(tiles_at_zoom):
        for y in range(tiles_at_zoom):
            coords.add((x, y))
    return coords


def incremental_build(parcels_dir: Path, output_dir: Path, force: bool = False):
    """Perform timestamp-based incremental build of world tiles."""
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Incremental World Tile Builder (Timestamp-based)        ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    if force:
        print("🔄 Force rebuild requested - regenerating all tiles")
        print()
        # Clear output directory
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Run full build
        from build_world import load_parcels, build_pyramid, build_label_pyramid
        
        parcels = load_parcels(parcels_dir)
        if not parcels:
            print("❌ No parcel images found!")
            return 1
        
        build_pyramid(parcels, output_dir)
        build_label_pyramid(output_dir)
        
        print("\n✅ Full build complete")
        return 0
    
    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Phase 1: Build zoom 6 tiles (check all grid positions)
    print(f"🔨 Phase 1: Zoom level {MAX_ZOOM} (checking all {GRID_SIZE}x{GRID_SIZE} positions)...")
    
    rebuilt_count = 0
    skipped_count = 0
    missing_parcel_count = 0
    
    # Build map of existing parcels
    parcel_map: Dict[Tuple[int, int], Path] = {}
    for parcel_path in parcels_dir.glob("*.png"):
        coords = parse_parcel_filename(parcel_path.name)
        if coords:
            parcel_map[coords] = parcel_path
    
    print(f"   Found {len(parcel_map)} parcel files")
    
    # Check all positions in the grid
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            tile_x = col + OFFSET
            tile_y = OFFSET + (GRID_SIZE - 1) - row
            
            # Check both image and label tiles
            image_tile_path = output_dir / "images" / "6" / str(tile_x) / f"{tile_y}.png"
            label_tile_path = output_dir / "labels" / "6" / str(tile_x) / f"{tile_y}.png"
            
            # Get parcel path (None if missing)
            parcel_path = parcel_map.get((row, col))
            
            # Determine if rebuild is needed
            # For missing parcels, we use mtime of 0, so tiles only rebuild if they don't exist
            if parcel_path:
                image_needs_rebuild = is_tile_out_of_date_zoom_6(parcel_path, image_tile_path)
                label_needs_rebuild = is_tile_out_of_date_zoom_6(parcel_path, label_tile_path)
            else:
                # Missing parcel - only rebuild if tiles don't exist
                image_needs_rebuild = not image_tile_path.exists()
                label_needs_rebuild = not label_tile_path.exists()
            
            if image_needs_rebuild or label_needs_rebuild:
                # Load parcel or use transparent pixel
                parcel_img = load_parcel_or_transparent(parcel_path)
                rebuild_tile_at_zoom_6(row, col, parcel_img, output_dir)
                rebuilt_count += 1
                if parcel_path is None:
                    missing_parcel_count += 1
            else:
                skipped_count += 1
    
    print(f"   Rebuilt: {rebuilt_count} (including {missing_parcel_count} empty), Up-to-date: {skipped_count}")
    print()
    
    # Phase 2: Build zoom levels 5 down to 0 (check child timestamps)
    for zoom in range(MAX_ZOOM - 1, MIN_ZOOM - 1, -1):
        print(f"🔨 Phase 2: Zoom level {zoom} (checking child timestamps)...")
        
        rebuilt_images = 0
        rebuilt_labels = 0
        skipped_images = 0
        skipped_labels = 0
        
        # Check all possible tiles at this zoom level
        tiles_at_zoom = 2 ** zoom
        
        for x in range(tiles_at_zoom):
            for y in range(tiles_at_zoom):
                # Check if image tile needs rebuild
                if is_tile_out_of_date(zoom, x, y, output_dir, "images"):
                    if rebuild_tile_at_zoom(zoom, x, y, output_dir, "images"):
                        rebuilt_images += 1
                else:
                    # Only count as skipped if the tile exists
                    image_tile_path = output_dir / "images" / str(zoom) / str(x) / f"{y}.png"
                    if image_tile_path.exists():
                        skipped_images += 1
                
                # Check if label tile needs rebuild
                if is_tile_out_of_date(zoom, x, y, output_dir, "labels"):
                    if rebuild_tile_at_zoom(zoom, x, y, output_dir, "labels"):
                        rebuilt_labels += 1
                else:
                    # Only count as skipped if the tile exists
                    label_tile_path = output_dir / "labels" / str(zoom) / str(x) / f"{y}.png"
                    if label_tile_path.exists():
                        skipped_labels += 1
        
        print(f"   Images - Rebuilt: {rebuilt_images}, Up-to-date: {skipped_images}")
        print(f"   Labels - Rebuilt: {rebuilt_labels}, Up-to-date: {skipped_labels}")
        print()
    
    total_rebuilt = rebuilt_count + sum([rebuilt_images, rebuilt_labels])
    
    if rebuilt_count == 0 and total_rebuilt == 0:
        print("✅ All tiles are up-to-date!")
    else:
        print(f"✅ Incremental build complete! ({total_rebuilt} tiles rebuilt)")
    
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
        '--force',
        action='store_true',
        help='Force full rebuild, clearing all existing tiles'
    )
    
    args = parser.parse_args()
    
    parcels_dir = Path(args.parcels_dir)
    output_dir = Path(args.output_dir)
    
    return incremental_build(parcels_dir, output_dir, args.force)


if __name__ == '__main__':
    sys.exit(main())
