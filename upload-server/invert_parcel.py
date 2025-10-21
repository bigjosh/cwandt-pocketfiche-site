#!/usr/bin/env python3
"""
Simple utility to invert colors in a parcel image file.
Swaps black (0) and white (1) pixels.
"""

import os
import sys
from pathlib import Path
from PIL import Image, ImageOps


def invert_parcel(data_dir: Path, parcel_location: str):
    """Invert colors in a parcel image file.
    
    Args:
        data_dir: Path to data directory
        parcel_location: Parcel location (e.g., 'A15')
    """
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
    
    if not parcel_file.exists():
        print(f"ERROR: Parcel file not found: {parcel_file}")
        sys.exit(1)
    
    print(f"Inverting: {parcel_file}")
    
    # Load image
    img = Image.open(parcel_file)
    
    # Invert colors
    inverted = ImageOps.invert(img.convert('RGB')).convert('1')
    
    # Save back to same file
    inverted.save(parcel_file, format='PNG', optimize=True)
    
    print("Done!")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python invert_parcel.py <parcel_location>")
        print("Example: python invert_parcel.py A15")
        sys.exit(1)
    
    parcel_location = sys.argv[1].strip().upper()
    
    # Get data directory from environment
    data_dir_str = os.environ.get('PF_DATA_DIR', '')
    if not data_dir_str:
        print("ERROR: PF_DATA_DIR environment variable not set")
        sys.exit(1)
    
    data_dir = Path(data_dir_str)
    if not data_dir.exists():
        print(f"ERROR: Data directory does not exist: {data_dir}")
        sys.exit(1)
    
    invert_parcel(data_dir, parcel_location)


if __name__ == '__main__':
    main()
