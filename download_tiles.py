#!/usr/bin/env python3
"""
Tile Downloader for Pocketfiche Community Parcels

Downloads 500x500 parcel tiles for parcels that are marked as claimed (claimed == 1)
via /api/claims.php, and saves them locally. By default also respects the claim
radius boundary unless --skip-radius-check is used.

Usage: python download-tiles.py [--server http://localhost:8000]
"""

import os
import sys
import math
import argparse
import requests
from pathlib import Path
from typing import Tuple, List, Set

# Constants from app.js
TILE_SIZE = 500
COLS = 38
ROWS = 38
WIDTH = COLS * TILE_SIZE
HEIGHT = ROWS * TILE_SIZE
CLAIM_RADIUS_PX = 9500
RADIUS_CENTER_X = WIDTH / 2
RADIUS_CENTER_Y = HEIGHT / 2


def col_to_letters(col: int) -> str:
    """
    Convert column number to Excel-style letters.
    0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA, 27 -> AB, etc.
    """
    result = ""
    col += 1  # Excel columns are 1-indexed
    while col > 0:
        col -= 1
        result = chr(65 + (col % 26)) + result
        col //= 26
    return result


def parcel_center(col: int, row: int) -> Tuple[float, float]:
    """Get the center coordinates of a parcel."""
    x = col * TILE_SIZE + TILE_SIZE / 2
    y = row * TILE_SIZE + TILE_SIZE / 2
    return (x, y)


def is_inside_radius(col: int, row: int) -> bool:
    """Check if parcel is inside the claimable radius."""
    x, y = parcel_center(col, row)
    dx = x - RADIUS_CENTER_X
    dy = y - RADIUS_CENTER_Y
    distance = math.hypot(dx, dy)
    return distance <= CLAIM_RADIUS_PX


def fetch_claimed_parcels(server_url: str) -> List[Tuple[int, int]]:
    """
    Fetch the claim map from /api/claims.php and return a list of (col, row)
    for parcels where claimed == 1. Handles both 'row_idx' and 'row' field names.
    """
    url = f"{server_url}/api/claims.php"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json() if r.headers.get('Content-Type', '').lower().startswith('application/json') else r.json()
    except Exception as e:
        print(f"❌ Failed to fetch claims from {url}: {e}")
        return []

    claimed: List[Tuple[int, int]] = []
    rows = data.get('claims', []) if isinstance(data, dict) else []
    for item in rows:
        try:
            col = int(item.get('col'))
            row_val = item.get('row_idx') if ('row_idx' in item) else item.get('row')
            row = int(row_val)
            claimed_flag = int(item.get('claimed', 0))
        except (TypeError, ValueError):
            continue
        if claimed_flag == 1:
            claimed.append((col, row))
    return claimed


def download_tile(server_url: str, col: int, row: int, output_dir: Path) -> bool:
    """
    Download a single tile from the server.
    
    Returns True if successful, False otherwise.
    """
    # Generate filename: tile-{alphanumeric_row}{column}.png
    # Note: Using row letter and column number as specified
    row_letter = col_to_letters(row)  # Row gets letters
    filename = f"{row_letter}{col}.png"  # Format: tile-A5.png  
    output_path = output_dir / filename
    
    # Construct URL
    url = f"{server_url}/api/tile.php?c={col}&r={row}"
    
    try:
        response = requests.get(url, timeout=10)
        
        # Check if we got a valid image
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            
            # Check if it's actually an image
            if 'image' in content_type:
                # Check if it's not just a 1x1 transparent pixel (empty tile)
                if len(response.content) > 100:  # Real tiles are much larger
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    return True
                else:
                    # Empty/transparent tile - skip
                    return False
            else:
                # Not an image response
                return False
        else:
            return False
            
    except requests.RequestException as e:
        print(f"Error downloading tile c={col} r={row}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Download all available parcel tiles from the server'
    )
    parser.add_argument(
        '--server',
        default='http://localhost:8000',
        help='Server URL (default: http://localhost:8000)'
    )
    parser.add_argument(
        '--output',
        default='tiles',
        help='Output directory (default: tiles)'
    )
    parser.add_argument(
        '--skip-radius-check',
        action='store_true',
        help='Download all tiles, even outside radius'
    )
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Pocketfiche Tile Downloader                              ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"Server:       {args.server}")
    print(f"Output dir:   {output_dir.absolute()}")
    print(f"Grid size:    {COLS} × {ROWS}")
    print(f"Tile size:    {TILE_SIZE}×{TILE_SIZE} pixels")
    print(f"Radius check: {'Disabled' if args.skip_radius_check else 'Enabled'}")
    print()
    
    # Test server connection
    print("🔍 Testing server connection...")
    try:
        response = requests.get(f"{args.server}/api/claims.php", timeout=5)
        if response.status_code == 200:
            print("✅ Server is reachable")
        else:
            print(f"⚠️  Server returned status {response.status_code}")
    except requests.RequestException as e:
        print(f"❌ Cannot connect to server: {e}")
        print("   Make sure the server is running!")
        return 1
    
    print()
    print("📥 Downloading tiles...")
    print()
    
    stats = {
        'total': 0,
        'downloaded': 0,
        'skipped_radius': 0,
        'skipped_empty': 0,
        'errors': 0,
        'overwritten': 0
    }
    
    # Build the list of claimed parcels
    print("🔎 Fetching claim map (claimed == 1)…")
    claimed_parcels = fetch_claimed_parcels(args.server)
    claimed_set: Set[Tuple[int, int]] = set(claimed_parcels)

    if not claimed_set:
        print("✓ No claimed parcels found — nothing to download.")
        print()
        return 0

    # Optionally filter by radius
    if args.skip_radius_check:
        to_check: List[Tuple[int, int]] = sorted(claimed_set)
        skipped_radius = 0
    else:
        to_check = sorted([(c, r) for (c, r) in claimed_set if is_inside_radius(c, r)])
        skipped_radius = len(claimed_set) - len(to_check)

    print(f"Tiles to check (claimed only): {len(to_check)}")
    if skipped_radius:
        print(f"(Skipped by radius: {skipped_radius})")
    print()

    # Download tiles (claimed only)
    stats['total'] = len(to_check)
    stats['skipped_radius'] += skipped_radius

    for (col, row) in to_check:
        # Track if file already exists (for stats)
        row_letter = col_to_letters(row)
        filename = f"tile-{row_letter}{col}.png"
        output_path = output_dir / filename
        
        already_existed = output_path.exists()

        # Try to download (will overwrite if exists)
        success = download_tile(args.server, col, row, output_dir)

        if success:
            stats['downloaded'] += 1
            if already_existed:
                stats['overwritten'] += 1
                print(f"🔄 {filename:15} (col={col:2d}, row={row:2d}) [overwritten]")
            else:
                print(f"✅ {filename:15} (col={col:2d}, row={row:2d})")
        else:
            stats['skipped_empty'] += 1
            # Don't print empty tiles to reduce noise
    
    print()
    print("════════════════════════════════════════════════════════════")
    print("📊 Summary")
    print("════════════════════════════════════════════════════════════")
    print(f"Total parcels:       {stats['total']}")
    print(f"Downloaded:          {stats['downloaded']} ✅")
    print(f"Overwritten:         {stats['overwritten']}")
    print(f"Skipped (radius):    {stats['skipped_radius']}")
    print(f"Skipped (empty):     {stats['skipped_empty']}")
    print(f"Errors:              {stats['errors']}")
    print("════════════════════════════════════════════════════════════")
    print()
    
    if stats['downloaded'] > 0:
        print(f"🎉 Successfully downloaded {stats['downloaded']} tile(s)!")
        print(f"   Saved to: {output_dir.absolute()}")
    else:
        print("✓ No new tiles to download.")
    
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
