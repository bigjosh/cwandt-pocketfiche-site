#!/usr/bin/env python3
"""
Pocket Fische Upload Server - WSGI Application

API documented in README.md

Handles three types of commands:
1. Admin commands: generate-code, get-codes, delete-image, delete-location (requires admin-id parameter)
2. Backer commands: get-parcel, upload (requires code parameter)
3. Public commands: get-parcels (no auth required)

All data is stored in files in PF_DATA_DIR environment variable location.

Do not be temped to use only HTTP status codes to return errors, it caused me nothing but problems. Better to just return a JSON object with a status field.

Error handling:
- Request errors (bad auth, invalid input): HTTP error codes
- State errors (location taken, code used): JSON with status field
- Success: JSON with status='success'
"""

import io
import json
import math
import os
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import parse_qs
import mimetypes

from PIL import Image
# Allow loading of truncated images (sometimes happens during upload)
# ImageFile.LOAD_TRUNCATED_IMAGES = True

from werkzeug.formparser import parse_form_data
from werkzeug.datastructures import FileStorage

# Constants
CODE_LENGTH = 8
PARCEL_SIZE = 500
GRID_SIZE = 38
LABEL_MAX_DISTANCE = 19


def get_data_dir() -> Path:
    """Get data directory from environment variable.
    
    Returns:
        Path to data directory
        
    Raises:
        RuntimeError: If PF_DATA_DIR not set
    """
    data_dir_str = os.environ.get('PF_DATA_DIR', '')
    if not data_dir_str:
        raise RuntimeError('PF_DATA_DIR environment variable not set')
    
    data_dir = Path(data_dir_str)
    if not data_dir.exists():
        raise RuntimeError(f'Data directory does not exist: {data_dir}')
    
    return data_dir


def initialize_locks_dir(data_dir: Path) -> None:
    """Initialize locks directory by removing any stale locks from previous runs.
    
    This is called on startup to clean up any orphaned lock files that may have
    been left behind if a process crashed during claim.
    
    Args:
        data_dir: Path to data directory
    """
    locks_dir = data_dir / 'locks'
    
    # Remove entire locks directory if it exists
    if locks_dir.exists():
        import shutil
        shutil.rmtree(locks_dir)
    
    # Recreate empty locks directory
    locks_dir.mkdir(parents=True, exist_ok=True)


# Initialize locks directory on module load to clean up any orphaned locks
try:
    _data_dir = get_data_dir()
    initialize_locks_dir(_data_dir)
    print(f"INFO: Cleaned locks directory at {_data_dir / 'locks'}", file=sys.stderr)
except Exception as e:
    print(f"WARNING: Failed to initialize locks directory: {e}", file=sys.stderr)


def send_error(message: str, code: int = 400) -> Tuple[str, list, bytes]:
    """Send an error response.
    
    Args:
        message: Error message
        code: HTTP status code
        
    Returns:
        Tuple of (status, headers, body)
    """
    data = {'status': 'error', 'message': message, 'code': code}
    body = json.dumps(data).encode('utf-8')
    status = f'{code} Error'
    headers = [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Content-Length', str(len(body)))
    ]
    return (status, headers, body)


def send_json(data: dict) -> Tuple[str, list, bytes]:
    """Send a JSON response.
    
    Args:
        data: Dictionary to send as JSON
        
    Returns:
        Tuple of (status, headers, body)
    """
    body = json.dumps(data).encode('utf-8')
    headers = [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Content-Length', str(len(body)))
    ]
    return ('200 OK', headers, body)


def atomic_add_file(file_path: Path, content: str) -> Tuple[bool, Optional[str]]:
    """Atomically add a file. Returns (success, existing_content).
    
    Creates a temp file and tries to rename it to the target name.
    If rename fails, the file already exists.
    
    Args:
        file_path: Target file path
        content: Content to write
        
    Returns:
        Tuple of (success: bool, existing_content: str or None)
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use low-level file operations for atomicity
    temp_path = file_path.parent / f".tmp_{secrets.token_hex(8)}"
    
    try:
        # Create temp file with exclusive access
        fd = os.open(str(temp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(fd, content.encode('utf-8'))
        finally:
            os.close(fd)
        
        # Try to rename (atomic on most filesystems)
        try:
            # On Windows, check if target exists first
            if file_path.exists():
                temp_path.unlink()
                return (False, file_path.read_text(encoding='utf-8'))
            
            # Target doesn't exist, rename temp to target
            temp_path.rename(file_path)
            return (True, None)
            
        except FileExistsError:
            # Another process created it
            temp_path.unlink()
            return (False, file_path.read_text(encoding='utf-8'))
            
    except Exception:
        # Clean up temp file if it exists
        try:
            os.close(fd)
        except:
            pass
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
        print(f"DEBUG: Writing {len(content)} bytes to {file_path.name}", file=sys.stderr)
        temp_path.write_bytes(content)
        bytes_written = temp_path.stat().st_size
        print(f"DEBUG: Temp file size on disk: {bytes_written} bytes", file=sys.stderr)
        
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


def build_valid_parcel_locations() -> set:
    """Build set of valid parcel locations within the 19mm circle.
    
    Returns:
        Set of valid location strings (e.g., 'A1', 'B12', 'AL38')
    """
    valid_locations = set()
    center_row = (GRID_SIZE - 1) / 2  # 18.5
    center_col = (GRID_SIZE - 1) / 2  # 18.5
    
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            # Calculate Euclidean distance from center
            distance = math.sqrt(
                (row - center_row) ** 2 + (col - center_col) ** 2
            )
            
            # Skip parcels outside the circle
            if distance > LABEL_MAX_DISTANCE:
                continue
            
            # Convert row to letters (A, B, ..., Z, AA, AB, ..., AL)
            row_letters = index_to_letters(row)
            location = f"{row_letters}{col + 1}"
            valid_locations.add(location)
    
    return valid_locations


def index_to_letters(idx: int) -> str:
    """Convert 0-based index to Excel-style letters.
    
    Args:
        idx: 0-based index
        
    Returns:
        Letter string (A, B, ..., Z, AA, AB, ..., AL)
    """
    idx = idx + 1  # Convert to 1-based
    result = ''
    while idx > 0:
        idx -= 1
        result = chr(65 + (idx % 26)) + result
        idx = idx // 26
    return result


def validate_parcel_location(location: str) -> bool:
    """Validate parcel location format and check if it's within valid area.
    
    Args:
        location: Location string (e.g., 'A1', 'B12', 'AL38')
        
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
        
        # Convert to 1-bit black and white
        if img.mode != '1':
            # Convert to grayscale first
            img = img.convert('L')
            # Then to 1-bit with dithering
            img = img.convert('1')
        
        # Save as PNG
        output = io.BytesIO()
        img.save(output, format='PNG', optimize=True)
        converted_data = output.getvalue()
        
        print(f"DEBUG: Converted image size: {len(converted_data)} bytes", file=sys.stderr)
        
        # Sanity check: converted image should not be empty and not unreasonably large
        if len(converted_data) == 0:
            return (False, "Image conversion failed - empty output", None)
        if len(converted_data) > 10 * 1024 * 1024:  # 10MB max
            return (False, f"Converted image too large: {len(converted_data)} bytes", None)
        
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
    authorized = admin_file.exists()
    print(f"Admin auth check for `{admin_file}`: {authorized}", file=sys.stderr)
    return authorized


def generate_code() -> str:
    """Generate a random 8-character uppercase code.
    
    Returns:
        Random code string
    """
    return ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ2345689') for _ in range(CODE_LENGTH))


# Handler functions (keep same logic as CGI version)
# These now return (status, headers, body) tuples instead of calling send_json directly

def handle_generate_code(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle generate-code command (admin only)."""
    # Check admin authorization
    admin_id = form_data.get('admin-id', [''])[0]
    if not check_admin_auth(admin_id, data_dir):
        return send_json({'status': 'error', 'message': 'Not authorized', 'code': 401})
    
    # Get POST parameters
    backer_id = form_data.get('backer-id', [''])[0].strip()
    notes = form_data.get('notes', [''])[0].strip()
    parcel_location = form_data.get('parcel-location', [''])[0].strip().upper()
    
    if not backer_id:
        return send_json({'status': 'error', 'message': 'backer-id required', 'code': 400})
    
    # If parcel-location specified, validate it
    if parcel_location:
        if not validate_parcel_location(parcel_location):
            return send_json({'status': 'error', 'message': 'Invalid parcel location'})
    
    # Generate code and try to save it
    # Try up to 10 times in case of collision (very unlikely)
    for _ in range(10):
        code = generate_code()
        access_file = data_dir / 'access' / f'{code}.txt'
        
        if not access_file.exists():
            # Create access file
            access_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write backer-id, admin-name, notes to access file
            # Format: line 0 = backer-id, line 1 = admin-name, line 2 = notes (NO field name prefixes)
            # Get admin name from admin file
            admin_file = data_dir / 'admins' / f'{admin_id}.txt'
            if admin_file.exists():
                admin_name = admin_file.read_text(encoding='utf-8').split('\n', 1)[0].strip()
                if not admin_name:
                    admin_name = "[Could not read admin name]"
            else:
                admin_name = "[Could not read admin name]"
            
            # Write: line 0=backer_id, line 1=admin_name, line 2=notes
            content = f"{backer_id}\n{admin_name}\n{notes}"
            access_file.write_text(content, encoding='utf-8')
            
            # If parcel location specified, claim it using lock-based system
            if parcel_location:
                success, error_code = claim_parcel(parcel_location, code, data_dir)
                if not success:
                    # Failed to claim - delete the access file we just created
                    try:
                        access_file.unlink()
                    except Exception:
                        pass
                    return send_json({'status': 'error', 'message': error_code})
            
            return send_json({'status': 'success', 'code': code})
    
    return send_json({'status': 'error', 'message': 'Failed to generate unique code'})


def handle_get_codes(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle get-codes command (admin only)."""
    # Check admin authorization
    admin_id = form_data.get('admin-id', [''])[0]
    if not check_admin_auth(admin_id, data_dir):
        return send_json({'status': 'error', 'message': 'Not authorized', 'code': 401})
    
    # Read all access files
    access_dir = data_dir / 'access'
    if not access_dir.exists():
        return send_json({'status': 'success', 'codes': []})
    
    codes = []
    for access_file in access_dir.glob('*.txt'):
        code = access_file.stem
        
        # Get timestamp from file modification time
        timestamp = int(access_file.stat().st_mtime)
        
        # Read access file
        # Format: line 0 = backer-id, line 1 = admin-name, line 2+ = notes (can have newlines)
        content = access_file.read_text(encoding='utf-8')
        lines = content.split('\n', 2)
        backer_id = lines[0].strip() if len(lines) > 0 else ''
        admin_name = lines[1].strip() if len(lines) > 1 else ''
        notes = lines[2].strip() if len(lines) > 2 else ''
        
        # Check if location file exists
        location_file = data_dir / 'locations' / f'{code}.txt'
        parcel_location = ''
        if location_file.exists():
            parcel_location = location_file.read_text(encoding='utf-8').strip()
        
        # Check if parcel image exists
        status = 'free'
        if parcel_location:
            parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
            if parcel_file.exists():
                # Check if it's a placeholder (1x1 image)
                if is_placeholder_image(parcel_file):
                    status = 'placeholdered'
                else:
                    status = 'uploaded'
            else:
                status = 'claimed'
        
        codes.append({
            'code': code,
            'backer-id': backer_id,
            'admin-name': admin_name,
            'notes': notes,
            'parcel-location': parcel_location,
            'status': status,
            'timestamp': timestamp
        })
    
    return send_json({'status': 'success', 'codes': codes})


def handle_get_parcel(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle get-parcel command (backer only)."""
    # Get code parameter
    code = form_data.get('code', [''])[0].strip()
    if not code:
        return send_json({'status': 'error', 'message': 'code not found'})
    
    # Check if code exists in access directory
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        return send_json({'status': 'error', 'message': 'code not found'})
    
    # Check if this code has a location assigned
    location_file = data_dir / 'locations' / f'{code}.txt'
    if not location_file.exists():
        return send_json({'status': 'free', 'message': 'no location assigned'})
    
    # Get the parcel location
    parcel_location = location_file.read_text(encoding='utf-8').strip()
    
    # Check if actual parcel image file exists
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
    if parcel_file.exists() and not is_placeholder_image(parcel_file):
        # Real image has been uploaded
        return send_json({'status': 'uploaded', 'parcel-location': parcel_location})
    else:
        # Location claimed but image not uploaded yet
        return send_json({'status': 'claimed', 'parcel-location': parcel_location})


def handle_get_parcels(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle get-parcels command (public).
    
    Returns a list of all claimed parcel locations (locations assigned to codes).
    No authorization required.
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
    return send_json({'status': 'success', 'parcels': sorted(claimed_locations)})



def claim_parcel(parcel_location: str, code: str, data_dir: Path) -> Tuple[bool, Optional[str]]:
    """Attempt to claim a parcel location using lock-based atomic system.
    
    Uses a lock file to prevent race conditions during the claim process:
    1. Create lock file atomically
    2. Check if location already claimed by another code
    3. Create location file atomically
    4. Delete lock file
    
    Args:
        parcel_location: Parcel location to claim (e.g., 'A1', 'B12')
        code: Access code attempting to claim
        data_dir: Path to data directory
        
    Returns:
        Tuple of (success: bool, error_code: Optional[str])
        - (True, None) if claim succeeded
        - (False, error_code) if claim failed
        
        Error codes (can be used directly in response messages):
        - 'lock_contention': Someone else is claiming this location right now
        - 'already_claimed': Location already claimed by another code
        - 'code_used': This code already has a different location
    """
    location_file = data_dir / 'locations' / f'{code}.txt'
    lock_file = data_dir / 'locks' / f'{parcel_location}.txt'
    
    # Step 1: Try to atomically create lock file
    lock_success, _ = atomic_add_file(lock_file, code)
    if not lock_success:
        # Someone else is claiming this location right now
        # In practice you would need pretty amazing luck to see this.
        return (False, 'lock contention')
    
    try:
        # Step 2: Check if parcel location is already claimed by another code
        claiming_code = is_parcel_location_claimed(parcel_location, data_dir)
        if claiming_code and claiming_code != code:
            # Already claimed by a different code
            lock_file.unlink()  # Clean up lock
            return (False, 'parcel already claimed')
        
        # Step 3: Try to create location file atomically
        success, existing_content = atomic_add_file(location_file, parcel_location)
        
        if not success:
            # Code already used (shouldn't happen in normal flow, but handle race condition)
            lock_file.unlink()  # Clean up lock
            return (False, 'code already used')
        
        # Step 4: Success! Delete lock file
        lock_file.unlink()
        return (True, None)
        
    except Exception as e:
        # Clean up lock on any error
        try:
            lock_file.unlink()
        except:
            pass
        raise


def is_parcel_location_claimed(parcel_location: str, data_dir: Path) -> Optional[str]:
    """Check if a parcel location is already claimed by scanning all location files.

    NOT ATOMIC! You need another way to guard against races. 
    
    Args:
        parcel_location: Parcel location to check (e.g., 'A1', 'B12')
        data_dir: Path to data directory
        
    Returns:
        Access code that claimed this location, or None if not claimed
    """
    locations_dir = data_dir / 'locations'
    if not locations_dir.exists():
        return None
    
    # Scan all location files
    for location_file in locations_dir.glob('*.txt'):
        try:
            claimed_location = location_file.read_text(encoding='utf-8').strip()
            if claimed_location == parcel_location:
                # Extract code from filename (e.g., 'ABC12345.txt' -> 'ABC12345')
                code = location_file.stem
                return code
        except Exception:
            # Skip files that can't be read
            continue
    
    return None


def is_placeholder_image(parcel_file: Path) -> bool:
    """Check if a parcel image file is a placeholder (1x1 pixel).
    
    Args:
        parcel_file: Path to parcel image file
        
    Returns:
        True if file is a 1x1 placeholder, False otherwise
    """
    if not parcel_file.exists():
        return False
    
    try:
        img = Image.open(parcel_file)
        return img.size == (1, 1)
    except Exception:
        # If we can't open it, assume it's not a placeholder
        return False


def replace_with_placeholder(parcel_file: Path) -> None:
    """Atomically replace a parcel file with a 1x1 transparent placeholder PNG.
    
    Creates a placeholder and atomically swaps it with the existing file.
    This ensures the builder sees the timestamp change.
    
    Args:
        parcel_file: Path to parcel file to replace
        
    Raises:
        Exception: If replacement fails
    """
    # Create 1x1 transparent placeholder PNG
    placeholder = Image.new('RGBA', (1, 1), (255, 255, 255, 0))
    output = io.BytesIO()
    placeholder.save(output, format='PNG', optimize=True)
    placeholder_bytes = output.getvalue()
    
    # Atomically replace the parcel file with placeholder
    fd, temp_path = tempfile.mkstemp(dir=parcel_file.parent, suffix='.png')
    temp_path = Path(temp_path)
    
    try:
        os.write(fd, placeholder_bytes)
        os.close(fd)
        # Atomically replace
        temp_path.replace(parcel_file)
    except Exception as e:
        try:
            os.close(fd)
        except:
            pass
        if temp_path.exists():
            temp_path.unlink()
        raise


def delete_parcel_image(parcel_location: str, data_dir: Path) -> Tuple[bool, Optional[str]]:
    """Delete a parcel image file by replacing it with a 1x1 transparent placeholder.

    I KNOW this is ugly because we will have these empty parcels hanging around in the parcels directory,
    but we need to do something becuase therer is no way for the builder to notice the difference between
    "there is no parcel here" and "there was a parcel here but now it is deleted" without storing state somewhere.
    
    Uses atomic replacement to catch the extreemly unlikely race where one user deletes a parcel and in the *instant* between
    the delete and the new placeholder getting saved another user uploads to the same location. Sorry, I worry about these things. :)

    Args:
        parcel_location: Parcel location string (e.g., 'A1', 'B12', 'AL38')
        data_dir: Path to data directory
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
    if parcel_file.exists():
        try:
            replace_with_placeholder(parcel_file)
            return (True, None)
        except Exception as e:
            return (False, f'Failed to delete image: {e}')
    else:
        return (False, 'No image file found')


def handle_delete_image(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle delete-image command (admin only).
    
    Deletes the parcel image file, allowing the user to re-upload to the same location.
    Does not delete the location file, so the location remains claimed by the code.
    """
    # Check admin authorization
    admin_id = form_data.get('admin-id', [''])[0]
    if not check_admin_auth(admin_id, data_dir):
        return send_json({'status': 'error', 'message': 'Not authorized', 'code': 401})
    
    # Get code parameter
    code = form_data.get('code', [''])[0].strip()
    if not code:
        return send_json({'status': 'error', 'message': 'code required'})
    
    # Check if code exists
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        return send_json({'status': 'error', 'message': 'code not found'})
    
    # Get the location file
    location_file = data_dir / 'locations' / f'{code}.txt'
    if not location_file.exists():
        return send_json({'status': 'error', 'message': 'No location assigned to this code'})
    
    # Get the parcel location
    parcel_location = location_file.read_text(encoding='utf-8').strip()
    
    # Delete the parcel image file
    success, error_message = delete_parcel_image(parcel_location, data_dir)
    if success:
        return send_json({'status': 'success', 'message': 'Image deleted'})
    else:
        return send_json({'status': 'error', 'message': error_message})


def handle_delete_location(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle delete-location command (admin only).
    
    Deletes both the location file and the parcel image file.
    This makes the location available for others to claim and allows the user to pick a new location.
    """
    # Check admin authorization
    admin_id = form_data.get('admin-id', [''])[0]
    if not check_admin_auth(admin_id, data_dir):
        return send_json({'status': 'error', 'message': 'Not authorized', 'code': 401})
    
    # Get code parameter
    code = form_data.get('code', [''])[0].strip()
    if not code:
        return send_json({'status': 'error', 'message': 'code required'})
    
    # Check if code exists
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        return send_json({'status': 'error', 'message': 'code not found'})
    
    # Get the location file
    location_file = data_dir / 'locations' / f'{code}.txt'
    if not location_file.exists():
        return send_json({'status': 'error', 'message': 'No location assigned to this code'})
    
    # Get the parcel location
    parcel_location = location_file.read_text(encoding='utf-8').strip()
    
    # Delete both the location file and the parcel image file
    # Note that we delete the location first becuase then the image will be hanging so no
    # race condition can occur. But there is one failure mode if everything crashes exactly when 
    # the location file is deleted but the image file is not. In that case, the image will be 
    # hanging. I can live with that. :)
    try:
        # Delete location file first
        location_file.unlink()
        
        # Delete parcel image if it exists (ignore errors since location is already deleted)
        delete_parcel_image(parcel_location, data_dir)
        
        return send_json({'status': 'success', 'message': 'Location and image deleted'})
    except Exception as e:
        return send_json({'status': 'error', 'message': f'Failed to delete: {e}'})


def handle_upload(form_data: dict, file_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle upload command (backer only)."""
    # Get code parameter
    code = form_data.get('code', [''])[0].strip()
    if not code:
        return send_json({'status': 'error', 'message': 'Not authorized'})
    
    # Check if code exists in access directory
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        return send_json({'status': 'error', 'message': 'Not authorized'})
    
    # Get parcel location
    parcel_location = form_data.get('parcel-location', [''])[0].strip()
    if not parcel_location:
        return send_json({'status': 'error', 'message': 'Invalid location'})
    
    # Validate parcel location format
    if not validate_parcel_location(parcel_location):
        return send_json({'status': 'error', 'message': 'Invalid parcel location'})
    
    # Get image data from form
    if 'image' not in file_data:
        return send_json({'status': 'error', 'message': 'No image provided'})
    
    image_data = file_data['image']
    print(f"DEBUG: Received image size from client: {len(image_data)} bytes", file=sys.stderr)
    
    # Validate and convert image to 1-bit PNG
    is_valid, error_message, converted_image_data = validate_and_convert_image(image_data)
    if not is_valid:
        return send_json({'status': 'error', 'message': error_message})
    
    # Check if location file already exists (pre-assigned location)
    location_file = data_dir / 'locations' / f'{code}.txt'
    location_was_preassigned = location_file.exists()

    # there is an esoteric race condition here where the location file is deleted
    # between the time we check and the time we try to claim it. In that case, we
    # should just let the claim fail. The failure mode is that the parcel will be
    # left unclaimed. I don't care. 
    
    if location_was_preassigned:
        # Location was pre-assigned - verify it matches
        existing_location = location_file.read_text(encoding='utf-8').strip()
        if existing_location != parcel_location:
            return send_json({'status': 'error', 'message': 'Wrong location'})
    else:
        # No pre-assigned location - use lock-based claim to prevent race conditions
        success, error_code = claim_parcel(parcel_location, code, data_dir)
        if not success:
            # Handle 'code_used' specially to return 'used' status with correct location
            if error_code == 'code_used':
                # Code already has a different location - read it and return 'used' status
                try:
                    existing_location = location_file.read_text(encoding='utf-8').strip()
                    return send_json({'status': 'used', 'location': existing_location})
                except Exception:
                    # Fallback if we can't read the file
                    return send_json({'status': 'used', 'location': parcel_location})
            else:
                # For other errors, just return the error code as the message
                return send_json({'status': 'error', 'message': error_code})
    
    # Try to add parcel image file
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
    
    # Check if file exists and is a placeholder (allows re-upload after deletion)
    if parcel_file.exists() and is_placeholder_image(parcel_file):
        # It's a placeholder - atomically replace it with the new image
        try:
            # Create temp file in same directory
            fd, temp_path = tempfile.mkstemp(dir=parcel_file.parent, suffix='.png')
            temp_path = Path(temp_path)
            
            try:
                os.write(fd, converted_image_data)
                os.close(fd)
                # Atomically replace placeholder with new image
                temp_path.replace(parcel_file)
            except Exception as e:
                try:
                    os.close(fd)
                except:
                    pass
                if temp_path.exists():
                    temp_path.unlink()
                raise
                
        except Exception as e:
            # Failed to replace - rollback location file only if we created it
            if not location_was_preassigned:
                try:
                    location_file.unlink()
                except Exception as rollback_error:
                    print(f"WARNING: Failed to rollback location file: {rollback_error}", file=sys.stderr)
            return send_json({'status': 'error', 'message': f'Failed to save image: {e}'})
    else:
        # Try to add new parcel image file (no placeholder exists)
        success, file_existed = atomic_add_binary_file(parcel_file, converted_image_data)
        
        if not success:
            # Location already taken - rollback location file only if we created it
            if not location_was_preassigned:
                try:
                    location_file.unlink()
                except Exception as e:
                    print(f"WARNING: Failed to rollback location file: {e}", file=sys.stderr)
            return send_json({'status': 'taken', 'location': parcel_location})
    
    # Success!
    return send_json({'status': 'success', 'location': parcel_location})


def serve_static_file(file_path: Path) -> Tuple[str, list, bytes]:
    """Serve a static file.
    
    Args:
        file_path: Path to the file to serve
        
    Returns:
        Tuple of (status, headers, body)
    """
    try:
        # Check if file exists
        if not file_path.exists() or not file_path.is_file():
            body = b'404 Not Found'
            headers = [
                ('Content-Type', 'text/plain'),
                ('Content-Length', str(len(body)))
            ]
            return ('404 Not Found', headers, body)
        
        # Read file
        body = file_path.read_bytes()
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = 'application/octet-stream'
        
        headers = [
            ('Content-Type', content_type),
            ('Content-Length', str(len(body)))
        ]
        
        return ('200 OK', headers, body)
        
    except Exception as e:
        body = f'Error reading file: {str(e)}'.encode('utf-8')
        headers = [
            ('Content-Type', 'text/plain'),
            ('Content-Length', str(len(body)))
        ]
        return ('500 Internal Server Error', headers, body)


def parse_multipart(environ) -> Tuple[dict, dict]:
    """Parse multipart form data from WSGI environ.
    
    Returns:
        Tuple of (form_data dict, file_data dict)
    """
    # Use werkzeug for better multipart handling
    stream, form, files = parse_form_data(environ)
    
    # Convert to dict format
    form_data = {}
    for key in form.keys():
        form_data[key] = form.getlist(key)
    
    file_data = {}
    for key in files.keys():
        file_storage = files[key]
        file_data[key] = file_storage.read()
    
    return (form_data, file_data)


def application(environ, start_response):
    """WSGI application entry point."""
    try:
        # Log request
        method = environ.get('REQUEST_METHOD', 'GET')
        path = environ.get('PATH_INFO', '/')
        query_string = environ.get('QUERY_STRING', '')
        print(f"DEBUG: {method} {path}{'?' + query_string if query_string else ''}", file=sys.stderr)
        
        # Check if this is a static file request (no command parameter)
        # This handles requests like /admin.html or /upload.html
        if method == 'GET' and 'command=' not in query_string:
            # Strip leading slash
            requested_file = path.lstrip('/')
            
            # If no file specified or root, don't serve anything
            if not requested_file or requested_file == '/':
                status, headers, body = send_error('No file specified', 400)
                start_response(status, headers)
                return [body]
            
            # Security: Only allow serving files from the app directory
            # No directory traversal allowed
            if '..' in requested_file or requested_file.startswith('/'):
                status, headers, body = send_error('Invalid file path', 403)
                start_response(status, headers)
                return [body]
            
            # Get the directory where this script is located
            app_dir = Path(__file__).parent
            file_path = app_dir / requested_file
            
            # Serve the static file
            status, headers, body = serve_static_file(file_path)
            start_response(status, headers)
            return [body]
        
        # API request - get data directory
        data_dir = get_data_dir()
        
        # Parse form data
        if method == 'POST':
            form_data, file_data = parse_multipart(environ)
        elif method == 'GET':
            # Parse query string
            form_data = parse_qs(query_string)
            file_data = {}
        else:
            status, headers, body = send_error('Method not allowed', 405)
            start_response(status, headers)
            return [body]
        
        # Get command parameter
        command = form_data.get('command', [''])[0].strip()
        
        # Route to appropriate handler
        if command == 'generate-code':
            status, headers, body = handle_generate_code(form_data, data_dir)
        elif command == 'get-codes':
            status, headers, body = handle_get_codes(form_data, data_dir)
        elif command == 'get-parcel':
            status, headers, body = handle_get_parcel(form_data, data_dir)
        elif command == 'get-parcels':
            status, headers, body = handle_get_parcels(form_data, data_dir)
        elif command == 'delete-image':
            status, headers, body = handle_delete_image(form_data, data_dir)
        elif command == 'delete-location':
            status, headers, body = handle_delete_location(form_data, data_dir)
        elif command == 'upload':
            status, headers, body = handle_upload(form_data, file_data, data_dir)
        else:
            status, headers, body = send_error(f'Unknown command: {command}', 400)
        
        # Send response
        start_response(status, headers)
        return [body]
        
    except Exception as e:
        # Catch all unhandled exceptions
        print(f"ERROR: Unhandled exception: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        
        status, headers, body = send_error(f'Internal server error: {str(e)}', 500)
        start_response(status, headers)
        return [body]


if __name__ == '__main__':
    # For testing only
    from wsgiref.simple_server import make_server
    print("Starting test server on http://localhost:8000")
    print("Set PF_DATA_DIR environment variable before running")
    server = make_server('localhost', 8000, application)
    server.serve_forever()
