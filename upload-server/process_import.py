#!/usr/bin/env python3
"""
Process import.json to extract users with claimed_count > 0
and prepare data for generating access codes via app.py CGI interface.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from urllib.parse import urlencode


def load_import_data(file_path: Path) -> dict:
    """Load and parse the import.json file.
    
    Args:
        file_path: Path to import.json
        
    Returns:
        Parsed JSON data
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def filter_users_with_claims(data: dict) -> List[Dict]:
    """Filter users where claimed_count > 0.
    
    Args:
        data: Full import data
        
    Returns:
        List of users with claims
    """
    if not data.get('ok'):
        raise ValueError("Import data status is not OK")
    
    users = data.get('users', [])
    filtered_users = [user for user in users if user.get('claimed_count', 0) > 0]
    
    return filtered_users


def parse_parcels(parcels_str: str) -> List[str]:
    """Parse the parcels string into individual parcel locations.
    
    Args:
        parcels_str: Comma-separated parcel locations (e.g., "R:18, S:18, T:18")
        
    Returns:
        List of parcel location strings with colons removed (e.g., ["R18", "S18", "T18"])
    """
    if not parcels_str:
        return []
    
    # Split by comma, strip whitespace, and remove colons
    return [p.strip().replace(':', '') for p in parcels_str.split(',')]


def generate_notes(user: Dict) -> str:
    """Generate notes field from user record with all non-null, non-empty fields.
    
    Args:
        user: User record dictionary
        
    Returns:
        Notes string with key: value pairs, one per line
    """
    notes_lines = []
    
    for key, value in user.items():
        # Skip null values and empty strings
        if value is None or value == '':
            continue
        
        # Convert value to string and add as key: value
        notes_lines.append(f"{key}: {value}")
    
    return '\n'.join(notes_lines)


def prepare_access_codes(users: List[Dict]) -> List[Dict]:
    """Prepare access code data for each user's parcels.
    
    Handles duplicate backer_numbers globally, and adds suffixes for users with multiple parcels.
    
    Args:
        users: List of users with claims
        
    Returns:
        List of access code records to create
    """
    # Track backer_number usage across all users to handle duplicates
    backer_number_count = defaultdict(int)
    
    access_codes = []
    
    for user in users:
        backer_number = user.get('backer_number')
        
        # Determine base backer_id
        if not backer_number:
            # Use email as fallback
            base_backer_id = user.get('email', f"user-{user['id']}")
        else:
            # Track how many times we've seen this backer_number across all users
            backer_number_count[backer_number] += 1
            count = backer_number_count[backer_number]
            
            # Add suffix for duplicate backer_numbers across different users
            if count == 1:
                base_backer_id = backer_number
            else:
                base_backer_id = f"{backer_number}-{count}"
        
        # Generate notes from user record (all non-null, non-empty fields)
        notes = generate_notes(user)
        
        # Parse parcel locations for this user
        parcel_locations = parse_parcels(user.get('parcels', ''))
        
        # Create an access code entry for each parcel
        for idx, parcel_location in enumerate(parcel_locations, start=1):
            # If user has only 1 parcel, use base_backer_id
            # If user has >1 parcel, add suffix: first gets base, then -2, -3, etc.
            if len(parcel_locations) == 1:
                backer_id = base_backer_id
            else:
                if idx == 1:
                    backer_id = base_backer_id
                else:
                    backer_id = f"{base_backer_id}-{idx}"
            
            access_code_data = {
                'user_id': user['id'],
                'username': user.get('username'),
                'email': user.get('email'),
                'backer_id': backer_id,
                'backer_name': user.get('backer_name', ''),
                'parcel_location': parcel_location,
                'notes': notes
            }
            access_codes.append(access_code_data)
    
    return access_codes


def generate_access_code_via_cgi(admin_id: str, backer_id: str, notes: str, parcel_location: str, data_dir: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """Call the CGI script to generate an access code.
    
    Args:
        admin_id: Admin ID for authentication
        backer_id: Backer ID for the access code
        notes: Notes for the access code
        parcel_location: Parcel location to pre-assign
        data_dir: Path to data directory
        
    Returns:
        Tuple of (success, generated_code, error_message)
    """
    cgi_script = Path(__file__).parent / 'cgi-bin' / 'app.py'
    
    # Prepare environment
    env = os.environ.copy()
    env['PF_DATA_DIR'] = str(data_dir)
    env['REQUEST_METHOD'] = 'POST'
    env['CONTENT_TYPE'] = 'application/x-www-form-urlencoded'
    
    # Prepare form data with proper URL encoding
    params = {
        'command': 'generate-code',
        'admin-id': admin_id,
        'backer-id': backer_id,
        'notes': notes,
        'parcel-location': parcel_location
    }
    form_data = urlencode(params)
    
    try:
        # Call CGI script
        result = subprocess.run(
            ['python', str(cgi_script)],
            input=form_data,
            capture_output=True,
            text=True,
            env=env
        )
        
        # Parse response (skip HTTP headers, get JSON)
        output = result.stdout
        # Split by double newline to separate headers from body
        parts = output.split('\n\n', 1)
        if len(parts) > 1:
            json_response = parts[1]
        else:
            json_response = output
        
        response = json.loads(json_response)
        
        if response.get('status') == 'success':
            return (True, response.get('code'), None)
        else:
            return (False, None, response.get('message', 'Unknown error'))
    
    except Exception as e:
        return (False, None, f"Exception: {str(e)}")


def dry_run(access_codes: List[Dict]) -> None:
    """Display what would be created without actually calling the CGI.
    
    Args:
        access_codes: List of access code records
    """
    print("\n" + "="*80)
    print("DRY RUN - Access Codes to be Generated")
    print("="*80 + "\n")
    
    print(f"Total access codes to generate: {len(access_codes)}\n")
    
    # Group by backer_id to show clearly
    by_backer = defaultdict(list)
    for code_data in access_codes:
        by_backer[code_data['backer_id']].append(code_data)
    
    shown_notes_count = 0
    max_notes_to_show = 3  # Show notes for first 3 users
    
    for backer_id, codes in sorted(by_backer.items()):
        print(f"Backer ID: {backer_id}")
        print(f"  Email: {codes[0]['email']}")
        print(f"  Backer Name: {codes[0]['backer_name']}")
        print(f"  Parcels to claim ({len(codes)}):")
        for code_data in codes:
            print(f"    - {code_data['parcel_location']}")
        
        # Show notes for first few users as sample
        if shown_notes_count < max_notes_to_show:
            print(f"  Notes (sample):")
            notes_preview = codes[0]['notes'][:200]  # First 200 chars
            if len(codes[0]['notes']) > 200:
                notes_preview += "..."
            for line in notes_preview.split('\n'):
                print(f"    {line}")
            shown_notes_count += 1
        
        print()


def generate_codes(access_codes: List[Dict], admin_id: str, data_dir: Path) -> None:
    """Actually generate access codes via CGI.
    
    Args:
        access_codes: List of access code records
        admin_id: Admin ID for authentication
        data_dir: Path to data directory
    """
    print("\n" + "="*80)
    print("GENERATING ACCESS CODES")
    print("="*80 + "\n")
    
    print(f"Total access codes to generate: {len(access_codes)}\n")
    
    success_count = 0
    error_count = 0
    generated_codes = []
    
    for idx, code_data in enumerate(access_codes, start=1):
        backer_id = code_data['backer_id']
        parcel_location = code_data['parcel_location']
        notes = code_data['notes']
        
        print(f"[{idx}/{len(access_codes)}] Generating code for {backer_id} -> {parcel_location}...", end=' ')
        
        success, generated_code, error_msg = generate_access_code_via_cgi(
            admin_id, backer_id, notes, parcel_location, data_dir
        )
        
        if success:
            print(f"✓ {generated_code}")
            success_count += 1
            generated_codes.append({
                'backer_id': backer_id,
                'parcel_location': parcel_location,
                'code': generated_code
            })
        else:
            print(f"✗ ERROR: {error_msg}")
            error_count += 1
    
    print("\n" + "="*80)
    print(f"COMPLETE: {success_count} succeeded, {error_count} failed")
    print("="*80 + "\n")
    
    # Save results to file
    results_file = Path(__file__).parent / 'generated_codes.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(generated_codes, f, indent=2)
    
    print(f"Results saved to: {results_file}")


def main():
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Process import.json and generate access codes')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be generated without actually creating codes')
    parser.add_argument('--admin-id', type=str, help='Admin ID for authentication (required for actual generation)')
    parser.add_argument('--data-dir', type=str, help='Path to PF_DATA_DIR (required for actual generation)')
    parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    # Path to import.json
    import_file = Path(__file__).parent / 'import.json'
    
    # Load data
    print(f"Loading data from {import_file}...")
    data = load_import_data(import_file)
    
    # Filter users with claims
    users_with_claims = filter_users_with_claims(data)
    print(f"Found {len(users_with_claims)} users with claimed_count > 0")
    
    # Prepare access codes
    access_codes = prepare_access_codes(users_with_claims)
    
    # Determine mode
    if args.dry_run or not args.admin_id or not args.data_dir:
        # Dry run mode
        if not args.dry_run and (not args.admin_id or not args.data_dir):
            print("\nWARNING: Missing --admin-id or --data-dir. Running in dry-run mode.")
            print("To actually generate codes, use: --admin-id <ID> --data-dir <PATH>\n")
        dry_run(access_codes)
    else:
        # Actual generation mode
        data_dir = Path(args.data_dir)
        if not data_dir.exists():
            print(f"ERROR: Data directory does not exist: {data_dir}")
            sys.exit(1)
        
        print(f"\nUsing data directory: {data_dir}")
        print(f"Using admin ID: {args.admin_id}")
        
        # Confirm before proceeding (unless --yes flag is used)
        if not args.yes:
            response = input(f"\nReady to generate {len(access_codes)} access codes. Continue? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                sys.exit(0)
        else:
            print(f"\nGenerating {len(access_codes)} access codes (--yes flag provided)...")
        
        generate_codes(access_codes, args.admin_id, data_dir)


if __name__ == '__main__':
    main()
