#!/usr/bin/env python3
"""
Pocket Fische Upload Server - WSGI Application

Handles two types of commands:
1. Admin commands: generate-code, get-codes (requires admin-id parameter)
2. Backer commands: get-parcel, upload (requires code parameter)

All data is stored in files in PF_DATA_DIR environment variable location.

Error handling:
- Request errors (bad auth, invalid input): HTTP error codes
- State errors (location taken, code used): JSON with status field
- Success: JSON with status='success'
"""

import io
import json
import math
import os
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import parse_qs
import mimetypes

try:
    from PIL import Image, ImageFile
    # Allow loading of truncated images (sometimes happens during upload)
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except ImportError:
    # Will error later if image validation is needed
    Image = None

# Try to import werkzeug for better multipart handling
try:
    from werkzeug.formparser import parse_form_data
    from werkzeug.datastructures import FileStorage
    HAS_WERKZEUG = True
except ImportError:
    # Fall back to cgi module
    import cgi
    HAS_WERKZEUG = False

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
        return send_error('Not authorized', 403)
    
    # Get backer-id (required)
    backer_id = form_data.get('backer-id', [''])[0].strip()
    if not backer_id:
        return send_error('Backer ID is required')
    
    # Get optional notes
    notes = form_data.get('notes', [''])[0].strip()
    
    # Get optional parcel-location
    parcel_location = form_data.get('parcel-location', [''])[0].strip().upper()
    if parcel_location and not validate_parcel_location(parcel_location):
        return send_error('Invalid parcel location')
    
    # Generate unique code
    max_attempts = 100
    for attempt in range(max_attempts):
        code = generate_code()
        access_file = data_dir / 'access' / f'{code}.txt'
        
        if not access_file.exists():
            # Create access file
            access_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write backer-id, optional notes, optional parcel-location
            content_lines = [backer_id]
            
            # Get admin name from admin file
            admin_file = data_dir / 'admins' / f'{admin_id}.txt'
            if admin_file.exists():
                admin_name = admin_file.read_text(encoding='utf-8').strip()
                content_lines.append(f"admin-name:{admin_name}")
            
            if notes:
                content_lines.append(f"notes:{notes}")
            
            access_file.write_text('\n'.join(content_lines), encoding='utf-8')
            
            # If parcel location specified, pre-assign it
            if parcel_location:
                location_file = data_dir / 'locations' / f'{code}.txt'
                location_file.parent.mkdir(parents=True, exist_ok=True)
                location_file.write_text(parcel_location, encoding='utf-8')
            
            return send_json({'status': 'success', 'code': code})
    
    return send_error('Failed to generate unique code after maximum attempts')


def handle_get_codes(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle get-codes command (admin only)."""
    # Check admin authorization
    admin_id = form_data.get('admin-id', [''])[0]
    if not check_admin_auth(admin_id, data_dir):
        return send_error('Not authorized', 403)
    
    # Read all access files
    access_dir = data_dir / 'access'
    if not access_dir.exists():
        return send_json({'status': 'success', 'codes': []})
    
    codes = []
    for access_file in access_dir.glob('*.txt'):
        code = access_file.stem
        
        # Read access file
        lines = access_file.read_text(encoding='utf-8').strip().split('\n')
        backer_id = lines[0] if lines else ''
        
        # Parse optional fields
        admin_name = ''
        notes = ''
        for line in lines[1:]:
            if line.startswith('admin-name:'):
                admin_name = line[len('admin-name:'):].strip()
            elif line.startswith('notes:'):
                notes = line[len('notes:'):].strip()
        
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
                status = 'uploaded'
            else:
                status = 'claimed'
        
        codes.append({
            'code': code,
            'backer-id': backer_id,
            'admin-name': admin_name,
            'notes': notes,
            'parcel-location': parcel_location,
            'status': status
        })
    
    return send_json({'status': 'success', 'codes': codes})


def handle_get_parcel(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle get-parcel command (backer only)."""
    # Get code parameter
    code = form_data.get('code', [''])[0].strip()
    if not code:
        return send_error('Not authorized')
    
    # Check if code exists
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        return send_error('Not authorized')
    
    # Check if location file exists
    location_file = data_dir / 'locations' / f'{code}.txt'
    if not location_file.exists():
        return send_json({'status': 'free'})
    
    parcel_location = location_file.read_text(encoding='utf-8').strip()
    
    # Check if parcel image exists
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
    if parcel_file.exists():
        return send_json({'status': 'uploaded', 'parcel-location': parcel_location})
    else:
        return send_json({'status': 'claimed', 'parcel-location': parcel_location})


def handle_get_parcels(form_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle get-parcels command (public)."""
    parcels_dir = data_dir / 'parcels'
    if not parcels_dir.exists():
        return send_json({'status': 'success', 'parcels': []})
    
    # Get list of claimed locations
    claimed_locations = []
    for parcel_file in parcels_dir.glob('*.png'):
        location = parcel_file.stem
        claimed_locations.append(location)
    
    return send_json({'status': 'success', 'parcels': sorted(claimed_locations)})


def handle_upload(form_data: dict, file_data: dict, data_dir: Path) -> Tuple[str, list, bytes]:
    """Handle upload command (backer only)."""
    # Get code parameter
    code = form_data.get('code', [''])[0].strip()
    if not code:
        return send_error('Not authorized')
    
    # Check if code exists in access directory
    access_file = data_dir / 'access' / f'{code}.txt'
    if not access_file.exists():
        return send_error('Not authorized')
    
    # Get parcel location
    parcel_location = form_data.get('parcel-location', [''])[0].strip()
    if not parcel_location:
        return send_error('Invalid location')
    
    # Validate parcel location format
    if not validate_parcel_location(parcel_location):
        return send_error('Invalid parcel location')
    
    # Get image data
    if 'image' not in file_data:
        return send_error('No image provided')
    
    image_data = file_data['image']
    print(f"DEBUG: Received image size from client: {len(image_data)} bytes", file=sys.stderr)
    
    # Validate and convert image to 1-bit PNG
    is_valid, error_message, converted_image_data = validate_and_convert_image(image_data)
    if not is_valid:
        return send_error(error_message)
    
    # Check if location file already exists (pre-assigned location)
    location_file = data_dir / 'locations' / f'{code}.txt'
    location_was_preassigned = location_file.exists()
    
    if location_was_preassigned:
        # Location was pre-assigned - verify it matches
        existing_location = location_file.read_text(encoding='utf-8').strip()
        if existing_location != parcel_location:
            return send_error('Wrong location')
    else:
        # No pre-assigned location - try to add location file
        success, existing_content = atomic_add_file(location_file, parcel_location)
        
        if not success:
            # Code already used
            existing_location = existing_content.strip() if existing_content else parcel_location
            return send_json({'status': 'used', 'location': existing_location})
    
    # Try to add parcel image file
    parcel_file = data_dir / 'parcels' / f'{parcel_location}.png'
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
    if HAS_WERKZEUG:
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
    else:
        # Fall back to cgi.FieldStorage
        from io import BytesIO
        
        # Create a file-like object from wsgi.input
        content_length = int(environ.get('CONTENT_LENGTH', 0))
        if content_length > 0:
            body = environ['wsgi.input'].read(content_length)
            environ['wsgi.input'] = BytesIO(body)
        
        form = cgi.FieldStorage(
            fp=environ['wsgi.input'],
            environ=environ,
            keep_blank_values=True
        )
        
        form_data = {}
        file_data = {}
        
        for key in form.keys():
            item = form[key]
            if item.filename:
                # File upload
                file_data[key] = item.file.read()
            else:
                # Regular field
                if key not in form_data:
                    form_data[key] = []
                form_data[key].append(item.value)
        
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
