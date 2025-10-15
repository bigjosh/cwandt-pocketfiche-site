#!/usr/bin/env python3
"""
Pocket Fische Upload Server - CGI Script Handler

Handles two types of commands:
1. Admin commands: generate-code (requires admin-id parameter)
2. Backer commands: upload (requires code parameter)

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
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Optional, Tuple

try:
    from PIL import Image
except ImportError:
    # Will error later if image validation is needed
    Image = None

# Enable CGI error reporting for debugging
cgitb.enable()

# Constants
PARCEL_SIZE = 500  # Parcel images are 500x500 pixels
CODE_LENGTH = 8    # Access codes are 8 uppercase letters
PARCEL_PATTERN = re.compile(r'^[A-Z]{1,2}\d{1,2}$')  # Matches A1 to AL38


def get_data_dir() -> Path:
    """Get the data directory from PF_DATA_DIR environment variable.
    
    Returns:
        Path to data directory
        
    Raises:
        SystemExit: If PF_DATA_DIR not set or doesn't exist
    """
    data_dir_str = os.environ.get('PF_DATA_DIR')
    if not data_dir_str:
        send_error(500, "PF_DATA_DIR environment variable not set")
        sys.exit(1)
    
    data_dir = Path(data_dir_str)
    if not data_dir.exists():
        send_error(500, f"PF_DATA_DIR does not exist: {data_dir}")
        sys.exit(1)
    
    return data_dir


def send_error(code: int, message: str) -> None:
    """Send an HTTP error response.
    
    Args:
        code: HTTP status code
        message: Error message to display
    """
    print(f"Status: {code}")
    print("Content-Type: text/plain; charset=utf-8")
    print()
    print(message)


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
    """Validate parcel location format (A1 to AL38, uppercase only).
    
    Args:
        location: Parcel location string
        
    Returns:
        True if valid, False otherwise
    """
    if not PARCEL_PATTERN.match(location):
        return False
    
    # Extract letter and number parts
    match = re.match(r'^([A-Z]+)(\d+)$', location)
    if not match:
        return False
    
    letters, num_str = match.groups()
    num = int(num_str)
    
    # Convert letters to column index (A=0, B=1, ..., Z=25, AA=26, ..., AL=37)
    col = 0
    for char in letters:
        col = (col * 26) + (ord(char) - ord('A') + 1)
    col -= 1  # Convert to 0-based
    
    # Valid range: columns 0-37 (A-AL), rows 1-38
    return 0 <= col <= 37 and 1 <= num <= 38


def validate_and_convert_image(image_data: bytes) -> Tuple[bool, Optional[str], Optional[bytes]]:
    """Validate and convert image to 500x500 1-bit black-and-white PNG.
    
    Accepts 500x500 PNG in any color mode and converts to 1-bit.
    
    Args:
        image_data: Image data bytes
        
    Returns:
        Tuple of (is_valid, error_message, converted_data)
        - is_valid: True if valid, False otherwise
        - error_message: None if valid, error description if invalid
        - converted_data: 1-bit PNG bytes if valid, None if invalid
    """
    if Image is None:
        # PIL not available, can't validate
        send_error(500, "Image validation not available (PIL not installed)")
        sys.exit(1)
    
    try:
        img = Image.open(io.BytesIO(image_data))
        
        # Check format
        if img.format != 'PNG':
            return (False, f"Image must be PNG format (received {img.format})", None)
        
        # Check size
        if img.size != (PARCEL_SIZE, PARCEL_SIZE):
            return (False, f"Image must be exactly {PARCEL_SIZE}x{PARCEL_SIZE} pixels (received {img.size[0]}x{img.size[1]})", None)
        
        # Convert to 1-bit black and white if needed
        # (Browser canvas creates RGBA PNGs, so we convert server-side)
        if img.mode != '1':
            # Convert to grayscale first
            img = img.convert('L')
            # Then to 1-bit with dithering
            img = img.convert('1')
        
        # Save as 1-bit PNG
        output = io.BytesIO()
        img.save(output, format='PNG')
        converted_data = output.getvalue()
        
        return (True, None, converted_data)
        
    except Exception as e:
        return (False, f"Failed to process image: {str(e)}", None)


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
    authorized = admin_file.exists()
    print(f"Admin `{admin_file}` {admin_id} authorized: {authorized}", file=sys.stderr)
    
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
        send_error(401, "Not authorized")
        return
    
    # Get POST parameters
    backer_id = form.getfirst('backer-id', '').strip()
    notes = form.getfirst('notes', '').strip()
    
    if not backer_id:
        send_error(400, "backer-id required")
        return
    
    # Generate code and try to save it
    # Try up to 10 times in case of collision (very unlikely)
    for _ in range(10):
        code = generate_code()
        access_file = data_dir / 'access' / f'{code}.txt'
        content = f"{backer_id}\n{notes}"
        
        success, _ = atomic_add_file(access_file, content)
        if success:
            send_json({'status': 'success', 'code': code})
            return
    
    # If we get here, we failed to generate a unique code
    send_json({'status': 'error', 'message': 'Failed to generate unique code'})


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
        send_json({'status': 'error', 'message': 'Invalid location format'})
        return
    
    # Get image data from form
    if 'image' not in form:
        send_json({'status': 'error', 'message': 'No image provided'})
        return
    
    file_item = form['image']
    if not file_item.file:
        send_json({'status': 'error', 'message': 'No image provided'})
        return
    
    image_data = file_item.file.read()
    
    # Validate and convert image to 1-bit PNG
    is_valid, error_message, converted_image_data = validate_and_convert_image(image_data)
    if not is_valid:
        send_json({'status': 'error', 'message': error_message})
        return
    
    # Try to add location file (prevents duplicate uploads with same code)
    location_file = data_dir / 'locations' / f'{code}.txt'
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
        # Location already taken - rollback location file
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
    elif command == 'upload':
        handle_upload(form, data_dir)
    else:
        send_error(400, f"Unknown command: {command}")


if __name__ == '__main__':
    main()
