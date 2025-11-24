#!/usr/bin/env python3
"""
One Big PNG (OBP) - World Composer

Creates a single full-resolution PNG of the entire world by composing all
individual parcel PNG files. The output is 19000x19000 pixels (38x38 parcels
at 500x500 pixels each). Areas without parcel files are transparent.

Requirements:
- Pillow: pip install Pillow
- pyoxipng (optional, recommended): pip install pyoxipng
  Falls back to PIL compression if not installed

Usage:
  python obp.py --parcels-dir parcels --output-file world.png
  python obp.py --parcels-dir parcels --output-file world.png --no-compress
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

try:
    import oxipng
except ImportError:
    oxipng = None

# Constants from incremental_build.py
TILE_SIZE = 500  # Each parcel is 500x500 pixels
GRID_SIZE = 38   # World is 38x38 parcels


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


def compress_png_with_oxipng(png_path: Path) -> tuple[int, int]:
    """Compress a PNG file losslessly with atomic file replacement.
    
    Args:
        png_path: Path to PNG file to compress
        
    Returns:
        Tuple of (original_size, compressed_size) in bytes
    """
    # Get original file size
    original_size = png_path.stat().st_size
    
    # Create temp file in same directory (ensures same filesystem for atomic rename)
    fd, temp_path = tempfile.mkstemp(dir=png_path.parent, suffix='.png')
    temp_path = Path(temp_path)
    
    # Close the file descriptor immediately (we'll use the path, not the descriptor)
    os.close(fd)
    
    try:
        oxipng.optimize(png_path, temp_path)
        
        # Get compressed file size
        compressed_size = temp_path.stat().st_size
        
        # Atomically replace original with compressed version
        # Path.replace() is atomic on both Unix and Windows
        temp_path.replace(png_path)
        
        return (original_size, compressed_size)
        
    except Exception:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise


def create_world_png(parcels_dir: Path, output_file: Path, compress: bool = True) -> int:
    """Create one big PNG from all parcel files.
    
    Args:
        parcels_dir: Directory containing parcel PNG files
        output_file: Output PNG file path
        compress: If True, compress the output PNG with oxipng
        
    Returns:
        0 on success, 1 on error
    """
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  One Big PNG (OBP) - World Composer                        ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"Parcels directory: {parcels_dir}")
    print(f"Output file: {output_file}")
    print()
    
    # Verify parcels directory exists
    if not parcels_dir.exists():
        print(f"❌ Error: Parcels directory does not exist: {parcels_dir}")
        return 1
    
    # Calculate world size
    world_size = GRID_SIZE * TILE_SIZE  # 38 * 500 = 19000 pixels
    print(f"🌍 Creating {world_size}x{world_size} pixel world PNG...")
    print()
    
    # Create transparent canvas
    world_img = Image.new('RGBA', (world_size, world_size), (0, 0, 0, 0))
    
    # Track statistics
    parcels_found = 0
    parcels_missing = 0
    
    # Iterate through all parcel positions
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            parcel_label = parcel_name(row, col)
            parcel_path = parcels_dir / f"{parcel_label}.png"
            
            # Calculate position in world image
            # Row 0 (A) is at the top, Row 37 (AL) is at the bottom
            x_pos = col * TILE_SIZE
            y_pos = row * TILE_SIZE
            
            if parcel_path.exists():
                # Load and paste parcel image
                try:
                    parcel_img = Image.open(parcel_path)
                    
                    # Convert to RGBA if needed
                    if parcel_img.mode != 'RGBA':
                        parcel_rgba = parcel_img.convert('RGBA')
                    else:
                        parcel_rgba = parcel_img
                    
                    # Paste into world image
                    world_img.paste(parcel_rgba, (x_pos, y_pos), parcel_rgba)
                    parcels_found += 1
                    
                    # Print progress every 100 parcels
                    if parcels_found % 100 == 0:
                        print(f"   Processed {parcels_found} parcels...")
                    
                except Exception as e:
                    print(f"⚠️  Warning: Could not load {parcel_label}: {e}")
                    parcels_missing += 1
            else:
                # Parcel doesn't exist - leave transparent
                parcels_missing += 1
    
    print(f"\n✅ Assembled {parcels_found} parcels ({parcels_missing} missing/transparent)")
    print()
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Save the world image
    print(f"💾 Saving to {output_file}...")
    world_img.save(output_file, 'PNG')
    
    file_size = output_file.stat().st_size
    print(f"   Saved: {file_size:,} bytes ({file_size / (1024 * 1024):.2f} MB)")
    print()
    
    # Compress if requested
    if compress:
        if oxipng is None:
            print("⚠️  Warning: pyoxipng not installed, skipping compression")
            print("   Install with: pip install pyoxipng")
        else:
            print("🗜️  Compressing with oxipng...")
            original_size, compressed_size = compress_png_with_oxipng(output_file)
            saved = original_size - compressed_size
            percent = ((original_size - compressed_size) / original_size * 100) if original_size > 0 else 0
            print(f"   {original_size:,} → {compressed_size:,} bytes ({percent:+.1f}%)")
            print(f"   Saved: {saved / 1024:.1f} KB")
            print()
    
    print("✅ World PNG created successfully!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Create one big PNG of the entire world from parcel files'
    )
    parser.add_argument(
        '--parcels-dir',
        required=True,
        help='Directory containing parcel PNG files'
    )
    parser.add_argument(
        '--output-file',
        required=True,
        help='Output PNG file path'
    )
    parser.add_argument(
        '--no-compress',
        action='store_true',
        help='Skip PNG compression'
    )
    
    args = parser.parse_args()
    
    parcels_dir = Path(args.parcels_dir)
    output_file = Path(args.output_file)
    compress = not args.no_compress
    
    return create_world_png(parcels_dir, output_file, compress)


if __name__ == '__main__':
    sys.exit(main())
