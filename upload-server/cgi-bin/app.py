#!/usr/bin/env python3
"""
Pocket Fische Upload Server - CGI Script Handler

Handles two types of commands:
1. Admin commands: generate-code, get-codes (requires admin-id parameter)
2. Backer commands: get-parcel, upload (requires code parameter)

All data is stored in files in PF_DATA_DIR environment variable location.

Error handling:
- Request errors (bad auth, invalid input): HTTP error codes
- State errors (location taken, code used): JSON with status field
- Success: JSON with status='success'

Usage:
  This script is invoked by the web server as a CGI script.
  Set PF_DATA_DIR environment variable to point to data directory.
"""

# Suppress deprecation warnings for cgi/cgitb modules (deprecated in Python 3.13)
# We continue to use them for simplicity in this CGI script
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

import cgi
import cgitb
import io
import json
import math
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

try:
    from PIL import Image, ImageFile
    # Allow loading of truncated images (sometimes happens during upload)
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except ImportError:
    # Will error later if image validation is needed
    Image = None

# Note: cgitb.enable() is NOT called here because it outputs HTML before Status line
# which breaks proper HTTP error code handling. Instead, we catch all exceptions in main().

# Constants
PARCEL_SIZE = 500  # Parcel images are 500x500 pixels
CODE_LENGTH = 8    # Access codes are 8 uppercase letters
GRID_SIZE = 38     # World is 38x38 parcels
LABEL_MAX_DISTANCE = 19  # Maximum Euclidean distance from center

# defines the 19mm circle of writeable area on the disk


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


def build_valid_parcel_locations():
    """Build set of valid parcel locations within the 19mm circle."""
    # Calculate center of the 38x38 grid (0-based indexing)
    valid_parcel_locations = set()

    center_row = (GRID_SIZE - 1) / 2  # 18.5
    center_col = (GRID_SIZE - 1) / 2  # 18.5
    
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            # Calculate Euclidean distance from center
            distance = math.sqrt((row - center_row) ** 2 + (col - center_col) ** 2)
            
            # Skip tiles that are too far from center
            if distance > LABEL_MAX_DISTANCE:
                continue
            
            # Convert row to letter(s): 0->A, 25->Z, 26->AA, 37->AL
            row_letters = letter_of_index(row)
            # Column is 1-based (1-38)
            location = f"{row_letters}{col + 1}"
            valid_parcel_locations.add(location)


    return valid_parcel_locations



def get_data_dir() -> Path:
    """Get the data directory from PF_DATA_DIR environment variable.
    
    Returns:
        Path to data directory
        
    Raises:
        SystemExit: If PF_DATA_DIR not set or doesn't exist
    """
    data_dir_str = os.environ.get('PF_DATA_DIR')
    if not data_dir_str:
        send_json({'status': 'error', 'message': 'PF_DATA_DIR environment variable not set', 'code': 500})
        sys.exit(1)
    
    data_dir = Path(data_dir_str)
    if not data_dir.exists():
        send_json({'status': 'error', 'message': f'PF_DATA_DIR does not exist: {data_dir}', 'code': 500})
        sys.exit(1)
    
    return data_dir


def send_error(code: int, message: str) -> None:
    """Send a JSON error response.
    
    Args:
        code: HTTP status code (for reference, not used)
        message: Error message to display
    """
    send_json({'status': 'error', 'message': message, 'code': code})


def send_json(data: dict) -> None:
    """Send a JSON response.
    
    Args:
        data: Dictionary to send as JSON
    """
    print("Content-Type: application/json; charset=utf-8")
    print()
    print(json.dumps(data))


def atomic_add_file(file_path: Path, content: str) -> Tuple[bool, Optional[str]]:
    """Atomically add a file. Returns (success, existing_content).
    
    Creates a temp file and tries to rename it to the target name.
    If rename fails, the file already exists.
    
    Args:
        file_path: Target file path
        content: Content to write
        
    Returns:
        Tuple of (success: bool, existing_content: str or None)
        If success=False, existing_content contains the content of existing file
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory
    temp_path = file_path.parent / f".tmp_{secrets.token_hex(8)}"
    
    try:
        # Write content to temp file
        temp_path.write_text(content, encoding='utf-8')
        
        # Try to rename (atomic operation on most filesystems)
        # This will fail if target already exists
        try:
            # On Windows, we need to check if file exists first
            if file_path.exists():
                # File already exists, read its content
                existing_content = file_path.read_text(encoding='utf-8')
                temp_path.unlink()  # Clean up temp file
                return (False, existing_content)
            
            # File doesn't exist, rename temp to target
            temp_path.rename(file_path)
            return (True, None)
            
        except FileExistsError:
            # File was created between our check and rename
            existing_content = file_path.read_text(encoding='utf-8')
            temp_path.unlink()  # Clean up temp file
            return (False, existing_content)
            
    except Exception as e:
        # Clean up temp file if it exists
        if temp_path.exists():
            temp_path.unlink()
        raise


def atomic_replace_file(file_path: Path, content: str) -> None:
    """Atomically replace a file's contents (or create if doesn't exist).
    
    Uses write-to-temp-then-rename pattern to ensure atomicity.
    The file is never missing during the operation.
    
    Args:
        file_path: Target file path
        content: Content to write
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory (ensures same filesystem for atomic rename)
    fd, temp_path = tempfile.mkstemp(dir=file_path.parent, text=True)
    temp_path = Path(temp_path)
    
    try:
        # Write content to temp file via file descriptor
        os.write(fd, content.encode('utf-8'))
        os.close(fd)
        
        # Atomically replace target file with temp file
        # os.replace() is guaranteed to be atomic on both Unix and Windows
        # and will overwrite the target if it exists
        temp_path.replace(file_path)
        
    except Exception as e:
        # Clean up temp file if it exists
        try:
            os.close(fd)
        except:
            pass
        if temp_path.exists():
            temp_path.unlink()
        raise


def atomic_add_binary_file(file_path: Path, content: bytes) -> Tuple[bool, bool]:
    """Atomically add a binary file. Returns (success, file_existed).
    
    Args:
        file_path: Target file path
        content: Binary content to write
        
    Returns:
        Tuple of (success: bool, file_existed: bool)
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory
    temp_path = file_path.parent / f".tmp_{secrets.token_hex(8)}"
    
    try:
        # Write content to temp file
        temp_path.write_bytes(content)
        
        # Try to rename (atomic operation on most filesystems)
        try:
            # On Windows, we need to check if file exists first
            if file_path.exists():
                temp_path.unlink()  # Clean up temp file
                return (False, True)
            
            # File doesn't exist, rename temp to target
            temp_path.rename(file_path)
            return (True, False)
            
        except FileExistsError:
            temp_path.unlink()  # Clean up temp file
            return (False, True)
            
    except Exception as e:
        # Clean up temp file if it exists
        if temp_path.exists():
            temp_path.unlink()
        raise


def validate_parcel_location(location: str) -> bool:
    """Validate parcel location against the list of valid locations.
    
    Args:
        location: Parcel location string
        
    Returns:
        True if valid, False otherwise
    """
    return location in build_valid_parcel_locations()


def validate_and_convert_image(image_data: bytes) -> Tuple[bool, Optional[str], Optional[bytes]]:
    """Validate an image and convert it to optimized 1-bit PNG.
    
    Args:
        image_data: Raw image bytes
        
    Returns:
        Tuple of (is_valid, error_message, converted_image_data)
    """
    try:
        print(f"DEBUG: validate_and_convert_image received {len(image_data)} bytes", file=sys.stderr)
        
        # Load image from bytes
        img = Image.open(io.BytesIO(image_data))
        print(f"DEBUG: PIL opened image: mode={img.mode}, size={img.size}, format={img.format}", file=sys.stderr)
        
        # Check format
        if img.format != 'PNG':
            return (False, f"Image must be PNG format (received {img.format})", None)
        
        # Check size
        if img.size != (PARCEL_SIZE, PARCEL_SIZE):
            return (False, f"Image must be exactly {PARCEL_SIZE}x{PARCEL_SIZE} pixels (received {img.size[0]}x{img.size[1]})", None)
        
        # Convert to 1-bit black and white, then make black pixels transparent
        # (Browser canvas creates RGBA PNGs, so we convert server-side)
        
        # Step 1: Convert to 1-bit to ensure only pure black (0) and pure white (255)
        if img.mode != '1':
            # Convert to grayscale first
            img = img.convert('L')
            # Then to 1-bit with dithering
            img = img.convert('1')
        
        # Step 2: Convert to RGBA to add transparency
        # img = img.convert('RGBA')
        
        # # Step 3: Get pixel data and make black transparent, white opaque
        # pixels = img.load()
        # for y in range(img.height):
        #     for x in range(img.width):
        #         r, g, b, a = pixels[x, y]
        #         if r == 0 and g == 0 and b == 0:
        #             # Pure black 
        #             pixels[x, y] = (0, 0, 0)
        #         else:
        #             # Pure white 
        #             pixels[x, y] = (255, 255, 255)
        
        # Save as PNG
        output = io.BytesIO()
        img.save(output, format='PNG', optimize=True)
        converted_data = output.getvalue()
        
        return (True, None, converted_data)
        
    except Exception as e:
        return (False, f"Failed to process image exception: {str(e)}", None)


def check_admin_auth(admin_id: str, data_dir: Path) -> bool:
    """Check if admin-id is valid.
    
    Args:
        admin_id: Admin ID to check
        data_dir: Path to data directory
        
    Returns:
        True if authorized, False otherwise
    """
    admin_file = data_dir / 'admins' / f'{admin_id}.txt'
    
    # Debug logging to stderr (not stdout, which is for HTTP response)
    # Never log the admin_id itself - only log the file path and result
    authorized = admin_file.exists()
    print(f"Admin auth check for `{admin_file}`: {authorized}", file=sys.stderr)
    
    return authorized


def generate_code() -> str:
    """Generate a random 8-character uppercase code.
    
    Returns:
        Random code string
    """
    # Use secrets for cryptographically strong random - skip 0 and 1 and 7 becuase they look like O and I
    return ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ2345689') for _ in range(CODE_LENGTH))


def handle_generate_code(form: cgi.FieldStorage, data_dir: Path) -> None:
    """Handle generate-code command (admin only).
    
    Args:
        form: CGI form data
        data_dir: Path to data directory
    """
    # Check admin authorization
    admin_id = form.getfirst('admin-id', '')
    if not check_admin_auth(admin_id, data_dir):
        send_json({'status': 'error', 'message': 'Not authorized', 'code': 401})
        return
    
    # Read admin-name from admin file (first line)
    admin_file = data_dir / 'admins' / f'{admin_id}.txt'
    try:
        creator_admin_name = admin_file.read_text(encoding='utf-8').split('\n', 1)[0].strip()
        if not creator_admin_name:
            # Empty file - use generic fallback, never expose admin_id
            creator_admin_name = "[Could not read admin name]"
    except Exception:
        # Error reading file - use generic fallback, never expose admin_id
        creator_admin_name = "[Could not read admin name]"
    
    # Get POST parameters
    backer_id = form.getfirst('backer-id', '').strip()
    notes = form.getfirst('notes', '').strip()
    parcel_location = form.getfirst('parcel-location', '').strip().upper()
    
    if not backer_id:
        send_json({'status': 'error', 'message': 'backer-id required', 'code': 400})
        return
    
    # If parcel-location specified, validate it
    if parcel_location:
        if not validate_parcel_location(parcel_location):
            send_json({'status': 'error', 'message': 'Invalid parcel location'})
            return
    
    # Generate code and try to save it
    # Try up to 10 times in case of collision (very unlikely)
    for _ in range(10):
        code = generate_code()
        access_file = data_dir / 'access' / f'{code}.txt'
        content = f"{backer_id}\n{creator_admin_name}\n{notes}"
        
        success, _ = atomic_add_file(access_file, content)
        if success:
            # If parcel-location specified, save it to locations/{code}.txt
            # Use atomic replace to allow overwrites for migration/re-assignment
            if parcel_location:
                location_file = data_dir / 'locations' / f'{code}.txt'
                try:
                    atomic_replace_file(location_file, parcel_location)
                except Exception as e:
                    send_json({'status': 'error', 'message': f'Failed to save location: {e}'})
                    return
            
            send_json({'status': 'success', 'code': code})
            return
    
    # If we get here, we failed to generate a unique code
    send_json({'status': 'error', 'message': 'Failed to generate unique code'})


def handle_get_codes(form: cgi.FieldStorage, data_dir: Path) -> None:
    """Handle get-codes command (admin only).
    
    Returns a list of all access codes with their details.
    
    Args:
        form: CGI form data
        data_dir: Path to data directory
    """
    # Check admin authorization
    admin_id = form.getfirst('admin-id', '')
    if not check_admin_auth(admin_id, data_dir):
        send_json({'status': 'error', 'message': 'Not authorized', 'code': 401})
        return
    
    # Get all access code files
    access_dir = data_dir / 'access'
    locations_dir = data_dir / 'locations'
    
    codes_list = []
    
    if access_dir.exists():
        for access_file in sorted(access_dir.glob('*.txt')):
            code = access_file.stem  # filename without .txt
            
            # Read backer-id, admin-name, and notes from access file
            # Format: line 1 = backer-id, line 2 = admin-name, rest = notes (can have newlines)
            content = access_file.read_text(encoding='utf-8')
            lines = content.split('\n', 2)
            backer_id = lines[0].strip() if len(lines) > 0 else ''
            creator_admin_name = lines[1].strip() if len(lines) > 1 else ''
            notes = lines[2].strip() if len(lines) > 2 else ''
            
            # Check if code has a location assigned
            location_file = locations_dir / f'{code}.txt'
            if location_file.exists():
                parcel_location = location_file.read_text(encoding='utf-8').strip()
                
                # Check if actual parcel image file exists
                parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
                if parcel_file.exists():
                    status = 'uploaded'
                else:
                    status = 'claimed'
            else:
                parcel_location = None
                status = 'free'
            
            # Build code info
            code_info = {
                'code': code,
                'backer-id': backer_id,
                'admin-name': creator_admin_name,
                'notes': notes,
                'status': status
            }
            
            if parcel_location:
                code_info['parcel-location'] = parcel_location
            
            codes_list.append(code_info)
    
    # Return JSON array
    send_json({'status': 'success', 'codes': codes_list})


def handle_get_parcel(form: cgi.FieldStorage, data_dir: Path) -> None:
    """Handle get-parcel command (backer only).
    
    Returns the parcel location for a given code.
    
    Args:
        form: CGI form data
        data_dir: Path to data directory
    """
    # Get code parameter
    code = form.getfirst('code', '').strip()
    if not code:
        send_json({'status': 'error', 'message': 'code not found'})
        return
    
    # Check if code exists in access directory
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        send_json({'status': 'error', 'message': 'code not found'})
        return
    
    # Check if this code has a location assigned
    location_file = data_dir / 'locations' / f'{code}.txt'
    if not location_file.exists():
        send_json({'status': 'free', 'message': 'no location assigned'})
        return
    
    # Get the parcel location
    parcel_location = location_file.read_text(encoding='utf-8').strip()
    
    # Check if actual parcel image file exists
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
    if parcel_file.exists():
        # Image has been uploaded
        send_json({'status': 'uploaded', 'parcel-location': parcel_location})
    else:
        # Location claimed but image not uploaded yet
        send_json({'status': 'claimed', 'parcel-location': parcel_location})


def handle_get_parcels(form: cgi.FieldStorage, data_dir: Path) -> None:
    """Handle get-parcels command (public).
    
    Returns a list of all claimed parcel locations (locations assigned to codes).
    No authorization required.
    
    Args:
        form: CGI form data
        data_dir: Path to data directory
    """
    locations_dir = data_dir / 'locations'
    
    # Use a set to ensure each location only appears once
    claimed_locations = set()
    
    if locations_dir.exists():
        for location_file in locations_dir.glob('*.txt'):
            # Read the parcel location from the file
            try:
                location = location_file.read_text(encoding='utf-8').strip()
                if location:
                    claimed_locations.add(location)
            except Exception:
                # Skip files that can't be read
                continue
    


    
    # Return JSON array of claimed parcel locations (sorted for consistency)
    send_json({'status': 'success', 'parcels': sorted(claimed_locations)})


def handle_upload(form: cgi.FieldStorage, data_dir: Path) -> None:
    """Handle upload command (backer only).
    
    Args:
        form: CGI form data
        data_dir: Path to data directory
    """
    # Get code parameter
    code = form.getfirst('code', '').strip()
    if not code:
        send_json({'status': 'error', 'message': 'Not authorized'})
        return
    
    # Check if code exists in access directory
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        send_json({'status': 'error', 'message': 'Not authorized'})
        return
    
    # Get parcel location
    parcel_location = form.getfirst('parcel-location', '').strip()
    if not parcel_location:
        send_json({'status': 'error', 'message': 'Invalid location'})
        return
    
    # Validate parcel location format
    if not validate_parcel_location(parcel_location):
        send_json({'status': 'error', 'message': 'Invalid parcel location'})
        return
    
    # Get image data from form
    if 'image' not in form:
        send_json({'status': 'error', 'message': 'No image provided'})
        return
    
    file_item = form['image']
    if not file_item.file:
        send_json({'status': 'error', 'message': 'No image provided'})
        return
    
    # Read image data in chunks to ensure we get everything (CGI/ARR buffering issue)
    # Force complete read by reading in loop until EOF
    chunks = []
    while True:
        chunk = file_item.file.read(8192)  # Read 8KB chunks
        if not chunk:
            break
        chunks.append(chunk)
    image_data = b''.join(chunks)
    
    # Log received image size for debugging
    print(f"DEBUG: Received image size from client: {len(image_data)} bytes (from {len(chunks)} chunks)", file=sys.stderr)
    
    # Validate and convert image to 1-bit PNG
    is_valid, error_message, converted_image_data = validate_and_convert_image(image_data)
    if not is_valid:
        send_json({'status': 'error', 'message': error_message})
        return
    
    # Check if location file already exists (pre-assigned location)
    location_file = data_dir / 'locations' / f'{code}.txt'
    location_was_preassigned = location_file.exists()
    
    if location_was_preassigned:
        # Location was pre-assigned - verify it matches
        existing_location = location_file.read_text(encoding='utf-8').strip()
        if existing_location != parcel_location:
            send_json({'status': 'error', 'message': 'Wrong location'})
            return
        # Location matches - continue to parcel file check (skip atomic_add_file)
    else:
        # No pre-assigned location - try to add location file (prevents duplicate uploads with same code)
        success, existing_content = atomic_add_file(location_file, parcel_location)
        
        if not success:
            # Code already used
            existing_location = existing_content.strip() if existing_content else parcel_location
            send_json({'status': 'used', 'location': existing_location})
            return
    
    # Try to add parcel image file (save converted 1-bit version)
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
    success, file_existed = atomic_add_binary_file(parcel_file, converted_image_data)
    
    if not success:
        # Location already taken - rollback location file only if we created it
        if not location_was_preassigned:
            location_file.unlink()
        send_json({'status': 'taken', 'location': parcel_location})
        return
    
    # Success!
    send_json({'status': 'success', 'location': parcel_location})


def main() -> None:
    """Main CGI script entry point."""
    # Get data directory
    data_dir = get_data_dir()
    
    # Parse form data
    form = cgi.FieldStorage()
    
    # Get command parameter
    command = form.getfirst('command', '').strip()
    
    if command == 'generate-code':
        handle_generate_code(form, data_dir)
    elif command == 'get-codes':
        handle_get_codes(form, data_dir)
    elif command == 'get-parcel':
        handle_get_parcel(form, data_dir)
    elif command == 'get-parcels':
        handle_get_parcels(form, data_dir)
    elif command == 'upload':
        handle_upload(form, data_dir)
    else:
        send_json({'status': 'error', 'message': f'Unknown command: {command}', 'code': 400})


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # Catch all unhandled exceptions and return JSON error
        send_json({'status': 'error', 'message': f'Internal server error: {str(e)}', 'code': 500})
