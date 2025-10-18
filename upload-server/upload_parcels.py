#!/usr/bin/env python3
"""
Upload parcel images for generated access codes.

This script:
1. Reads generated_codes.json
2. For each access code, checks if a parcel image exists
3. Uploads the image via the CGI upload command
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional


def load_generated_codes(file_path: Path) -> List[Dict]:
    """Load the generated codes from JSON file.
    
    Args:
        file_path: Path to generated_codes.json
        
    Returns:
        List of generated code records
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_parcel_image(parcel_location: str, parcels_dir: Path) -> Optional[Path]:
    """Find parcel image file for a given location.
    
    Args:
        parcel_location: Parcel location (e.g., "R18", "S18")
        parcels_dir: Directory containing parcel images
        
    Returns:
        Path to parcel image file if found, None otherwise
    """
    # Try .png extension (most common)
    png_file = parcels_dir / f"{parcel_location}.png"
    if png_file.exists():
        return png_file
    
    # Try other common extensions
    for ext in ['.jpg', '.jpeg', '.gif']:
        img_file = parcels_dir / f"{parcel_location}{ext}"
        if img_file.exists():
            return img_file
    
    return None


def upload_parcel_via_cgi(code: str, parcel_location: str, image_path: Path, data_dir: Path) -> Tuple[bool, Optional[str]]:
    """Upload a parcel image via CGI.
    
    Args:
        code: Access code
        parcel_location: Parcel location
        image_path: Path to image file
        data_dir: Path to data directory
        
    Returns:
        Tuple of (success, error_message)
    """
    cgi_script = Path(__file__).parent / 'cgi-bin' / 'app.py'
    
    # Read image file
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # Create a simple multipart form data
    # We'll use a Python script approach to simulate the upload
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    # Build multipart form data
    body_parts = []
    
    # Add command field
    body_parts.append(f'--{boundary}\r\n')
    body_parts.append('Content-Disposition: form-data; name="command"\r\n\r\n')
    body_parts.append('upload\r\n')
    
    # Add code field
    body_parts.append(f'--{boundary}\r\n')
    body_parts.append('Content-Disposition: form-data; name="code"\r\n\r\n')
    body_parts.append(f'{code}\r\n')
    
    # Add parcel-location field
    body_parts.append(f'--{boundary}\r\n')
    body_parts.append('Content-Disposition: form-data; name="parcel-location"\r\n\r\n')
    body_parts.append(f'{parcel_location}\r\n')
    
    # Add image field
    body_parts.append(f'--{boundary}\r\n')
    body_parts.append(f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n')
    body_parts.append('Content-Type: image/png\r\n\r\n')
    
    # Combine text parts
    body_text = ''.join(body_parts)
    body_bytes = body_text.encode('utf-8')
    
    # Add image data and closing boundary
    body_bytes += image_data
    body_bytes += f'\r\n--{boundary}--\r\n'.encode('utf-8')
    
    # Prepare environment
    env = os.environ.copy()
    env['PF_DATA_DIR'] = str(data_dir)
    env['REQUEST_METHOD'] = 'POST'
    env['CONTENT_TYPE'] = f'multipart/form-data; boundary={boundary}'
    env['CONTENT_LENGTH'] = str(len(body_bytes))
    
    try:
        # Call CGI script
        result = subprocess.run(
            ['python', str(cgi_script)],
            input=body_bytes,
            capture_output=True,
            env=env
        )
        
        # Parse response (skip HTTP headers, get JSON)
        output = result.stdout.decode('utf-8')
        stderr_output = result.stderr.decode('utf-8')
        
        # Debug: print raw output if there's an issue
        if result.returncode != 0:
            return (False, f"CGI script error (exit {result.returncode}): {stderr_output[:200]}")
        
        # Find the JSON - it starts after the first empty line (after headers)
        # Split lines and find where JSON starts
        lines = output.split('\n')
        json_start = 0
        for i, line in enumerate(lines):
            if line.strip() == '':
                json_start = i + 1
                break
        
        json_response = '\n'.join(lines[json_start:]).strip()
        
        # Check if we got any response
        if not json_response:
            return (False, f"Empty response. STDERR: {stderr_output[:200]}")
        
        try:
            response = json.loads(json_response)
        except json.JSONDecodeError as je:
            return (False, f"Invalid JSON: {json_response[:100]}")
        
        if response.get('status') == 'success':
            return (True, None)
        else:
            status = response.get('status', 'unknown')
            message = response.get('message', '')
            location = response.get('location', '')
            return (False, f"Status: {status}, Message: {message}, Location: {location}")
    
    except Exception as e:
        return (False, f"Exception: {str(e)}")


def upload_parcels(codes: List[Dict], parcels_dir: Path, data_dir: Path) -> None:
    """Upload parcel images for all generated codes.
    
    Args:
        codes: List of generated code records
        parcels_dir: Directory containing parcel images
        data_dir: Path to data directory
    """
    print("\n" + "="*80)
    print("UPLOADING PARCEL IMAGES")
    print("="*80 + "\n")
    
    print(f"Total codes to process: {len(codes)}")
    print(f"Looking for images in: {parcels_dir}\n")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for idx, code_data in enumerate(codes, start=1):
        code = code_data['code']
        parcel_location = code_data['parcel_location']
        backer_id = code_data['backer_id']
        
        # Check if image exists
        image_path = find_parcel_image(parcel_location, parcels_dir)
        
        if not image_path:
            print(f"[{idx}/{len(codes)}] {backer_id} -> {parcel_location}: No image found, skipping")
            skip_count += 1
            continue
        
        print(f"[{idx}/{len(codes)}] {backer_id} -> {parcel_location}: Uploading {image_path.name}...", end=' ')
        
        success, error_msg = upload_parcel_via_cgi(code, parcel_location, image_path, data_dir)
        
        if success:
            print(f"OK")
            success_count += 1
        else:
            print(f"FAIL: {error_msg}")
            error_count += 1
    
    print("\n" + "="*80)
    print(f"COMPLETE: {success_count} uploaded, {skip_count} skipped (no image), {error_count} failed")
    print("="*80)


def main():
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Upload parcel images for generated access codes')
    parser.add_argument('--codes-file', type=str, default='generated_codes.json', help='Path to generated_codes.json')
    parser.add_argument('--parcels-dir', type=str, required=True, help='Directory containing parcel images')
    parser.add_argument('--data-dir', type=str, required=True, help='Path to PF_DATA_DIR')
    parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    # Load generated codes
    codes_file = Path(__file__).parent / args.codes_file
    if not codes_file.exists():
        print(f"ERROR: Codes file not found: {codes_file}")
        sys.exit(1)
    
    print(f"Loading codes from {codes_file}...")
    codes = load_generated_codes(codes_file)
    print(f"Found {len(codes)} codes")
    
    # Validate directories
    parcels_dir = Path(args.parcels_dir)
    if not parcels_dir.exists():
        print(f"ERROR: Parcels directory does not exist: {parcels_dir}")
        sys.exit(1)
    
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"ERROR: Data directory does not exist: {data_dir}")
        sys.exit(1)
    
    # Confirm before proceeding
    if not args.yes:
        response = input(f"\nReady to upload parcel images. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
    else:
        print(f"\nProceeding with upload (--yes flag provided)...")
    
    upload_parcels(codes, parcels_dir, data_dir)


if __name__ == '__main__':
    main()
