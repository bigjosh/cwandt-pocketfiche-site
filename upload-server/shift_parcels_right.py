#!/usr/bin/env python3
"""
One-time utility to shift all parcels one square to the right.
A1 -> A2, A2 -> A3, etc.

This updates:
1. Parcel image filenames in parcels/ directory
2. Location data inside location files in locations/ directory

IMPORTANT: Run this with the server stopped to avoid conflicts.
"""

import os
import sys
from pathlib import Path
import shutil
from datetime import datetime


def parse_location(location: str) -> tuple[str, int]:
    """Parse a location string into row letters and column number.
    
    Args:
        location: Location string like 'A1', 'AB15', 'AL38'
        
    Returns:
        Tuple of (row_letters, column_number)
    """
    # Find where letters end and numbers begin
    i = 0
    while i < len(location) and location[i].isalpha():
        i += 1
    
    row_letters = location[:i]
    column_number = int(location[i:])
    
    return (row_letters, column_number)


def shift_location_right(location: str) -> str:
    """Shift a location one column to the right.
    
    Args:
        location: Original location (e.g., 'A1')
        
    Returns:
        Shifted location (e.g., 'A2')
    """
    row_letters, column_number = parse_location(location)
    new_column = column_number + 1
    return f"{row_letters}{new_column}"


def backup_directory(source_dir: Path, backup_suffix: str) -> Path:
    """Create a backup of a directory.
    
    Args:
        source_dir: Directory to backup
        backup_suffix: Suffix for backup directory name
        
    Returns:
        Path to backup directory
    """
    backup_dir = source_dir.parent / f"{source_dir.name}_{backup_suffix}"
    
    if backup_dir.exists():
        print(f"Removing existing backup: {backup_dir}")
        shutil.rmtree(backup_dir)
    
    print(f"Creating backup: {backup_dir}")
    shutil.copytree(source_dir, backup_dir)
    
    return backup_dir


def shift_parcels(data_dir: Path, dry_run: bool = True):
    """Shift all parcels one column to the right.
    
    Args:
        data_dir: Path to data directory
        dry_run: If True, only print what would be done without making changes
    """
    parcels_dir = data_dir / 'parcels'
    locations_dir = data_dir / 'locations'
    
    # Verify directories exist
    if not parcels_dir.exists():
        print(f"ERROR: Parcels directory not found: {parcels_dir}")
        return
    
    if not locations_dir.exists():
        print(f"ERROR: Locations directory not found: {locations_dir}")
        return
    
    # Create backups if not dry run
    if not dry_run:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        print("\n=== Creating Backups ===")
        backup_directory(parcels_dir, f"backup_{timestamp}")
        backup_directory(locations_dir, f"backup_{timestamp}")
        print()
    
    # Phase 1: Rename parcel files
    # We need to process in REVERSE column order to avoid overwriting
    # (e.g., rename A38.png first, then A37.png, etc.)
    print("=== Phase 1: Renaming Parcel Files ===")
    
    parcel_files = list(parcels_dir.glob('*.png'))
    
    # Parse and sort by column number (descending)
    parcel_locations = []
    for parcel_file in parcel_files:
        location = parcel_file.stem
        try:
            row_letters, column_number = parse_location(location)
            parcel_locations.append((column_number, location, parcel_file))
        except Exception as e:
            print(f"WARNING: Could not parse location {location}: {e}")
            continue
    
    # Sort by column number (descending) to process right-to-left
    parcel_locations.sort(reverse=True)
    
    parcel_renames = []
    for column_number, location, parcel_file in parcel_locations:
        new_location = shift_location_right(location)
        new_parcel_file = parcels_dir / f"{new_location}.png"
        
        parcel_renames.append((parcel_file, new_parcel_file))
        
        if dry_run:
            print(f"  Would rename: {parcel_file.name} -> {new_parcel_file.name}")
        else:
            print(f"  Renaming: {parcel_file.name} -> {new_parcel_file.name}")
            parcel_file.rename(new_parcel_file)
    
    print(f"Total parcel files to rename: {len(parcel_renames)}")
    print()
    
    # Phase 2: Update location file contents
    print("=== Phase 2: Updating Location File Contents ===")
    
    location_files = list(locations_dir.glob('*.txt'))
    
    location_updates = []
    for location_file in location_files:
        try:
            # Read current location
            current_location = location_file.read_text(encoding='utf-8').strip()
            
            # Shift it right
            new_location = shift_location_right(current_location)
            
            location_updates.append((location_file, current_location, new_location))
            
            if dry_run:
                print(f"  Would update {location_file.name}: {current_location} -> {new_location}")
            else:
                print(f"  Updating {location_file.name}: {current_location} -> {new_location}")
                location_file.write_text(new_location, encoding='utf-8')
                
        except Exception as e:
            print(f"WARNING: Could not update {location_file.name}: {e}")
            continue
    
    print(f"Total location files to update: {len(location_updates)}")
    print()
    
    # Summary
    print("=== Summary ===")
    print(f"Parcel files renamed: {len(parcel_renames)}")
    print(f"Location files updated: {len(location_updates)}")
    
    if dry_run:
        print("\n*** DRY RUN - No changes were made ***")
        print("Run with --execute to apply changes")
    else:
        print("\n*** Changes applied successfully ***")
        print(f"Backups created with timestamp: {timestamp}")


def main():
    """Main entry point."""
    # Get data directory from environment or command line
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        data_dir_str = sys.argv[1]
    else:
        data_dir_str = os.environ.get('PF_DATA_DIR', '')
    
    if not data_dir_str:
        print("ERROR: Please specify data directory:")
        print("  python shift_parcels_right.py <data_dir> [--execute]")
        print("  or set PF_DATA_DIR environment variable")
        sys.exit(1)
    
    data_dir = Path(data_dir_str)
    
    if not data_dir.exists():
        print(f"ERROR: Data directory does not exist: {data_dir}")
        sys.exit(1)
    
    # Check for --execute flag
    dry_run = '--execute' not in sys.argv
    
    print("=" * 60)
    print("PARCEL SHIFT UTILITY")
    print("=" * 60)
    print(f"Data directory: {data_dir}")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (will make changes)'}")
    print()
    
    if not dry_run:
        print("WARNING: This will modify your data files!")
        print("Backups will be created, but please ensure server is stopped.")
        response = input("Type 'yes' to continue: ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
        print()
    
    shift_parcels(data_dir, dry_run)


if __name__ == '__main__':
    main()
