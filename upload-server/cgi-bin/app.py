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

# Note: cgitb.enable() is NOT called here because it outputs HTML before Status line
# which breaks proper HTTP error code handling. Instead, we catch all exceptions in main().

# Constants
PARCEL_SIZE = 500  # Parcel images are 500x500 pixels
CODE_LENGTH = 8    # Access codes are 8 uppercase letters
PARCEL_PATTERN = re.compile(r'^[A-Z]{1,2}\d{1,2}$')  # Matches A1 to AL38

# defines the 19mm circle of writeable area on the disk
valid_parcel_locations = {'A10', 'A11', 'A12', 'A13', 'A14', 'A15', 'A16', 'A17', 'A18', 'A19', 'A20', 'A21', 'A22', 'A23', 'A24', 'A25', 'A26', 'A27', 'A28', 'A29', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B14', 'B15', 'B16', 'B17', 'B18', 'B19', 'B20', 'B21', 'B22', 'B23', 'B24', 'B25', 'B26', 'B27', 'B28', 'B29', 'B30', 'B31', 'C6', 'C7', 'C8', 'C9', 'C10', 'C11', 'C12', 'C13', 'C14', 'C15', 'C16', 'C17', 'C18', 'C19', 'C20', 'C21', 'C22', 'C23', 'C24', 'C25', 'C26', 'C27', 'C28', 'C29', 'C30', 'C31', 'C32', 'C33', 'D5', 'D6', 'D7', 'D8', 'D9', 'D10', 'D11', 'D12', 'D13', 'D14', 'D15', 'D16', 'D17', 'D18', 'D19', 'D20', 'D21', 'D22', 'D23', 'D24', 'D25', 'D26', 'D27', 'D28', 'D29', 'D30', 'D31', 'D32', 'D33', 'D34', 'E4', 'E5', 'E6', 'E7', 'E8', 'E9', 'E10', 'E11', 'E12', 'E13', 'E14', 'E15', 'E16', 'E17', 'E18', 'E19', 'E20', 'E21', 'E22', 'E23', 'E24', 'E25', 'E26', 'E27', 'E28', 'E29', 'E30', 'E31', 'E32', 'E33', 'E34', 'E35', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12', 'F13', 'F14', 'F15', 'F16', 'F17', 'F18', 'F19', 'F20', 'F21', 'F22', 'F23', 'F24', 'F25', 'F26', 'F27', 'F28', 'F29', 'F30', 'F31', 'F32', 'F33', 'F34', 'F35', 'F36', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9', 'G10', 'G11', 'G12', 'G13', 'G14', 'G15', 'G16', 'G17', 'G18', 'G19', 'G20', 'G21', 'G22', 'G23', 'G24', 'G25', 'G26', 'G27', 'G28', 'G29', 'G30', 'G31', 'G32', 'G33', 'G34', 'G35', 'G36', 'G37', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8', 'H9', 'H10', 'H11', 'H12', 'H13', 'H14', 'H15', 'H16', 'H17', 'H18', 'H19', 'H20', 'H21', 'H22', 'H23', 'H24', 'H25', 'H26', 'H27', 'H28', 'H29', 'H30', 'H31', 'H32', 'H33', 'H34', 'H35', 'H36', 'H37', 'I1', 'I2', 'I3', 'I4', 'I5', 'I6', 'I7', 'I8', 'I9', 'I10', 'I11', 'I12', 'I13', 'I14', 'I15', 'I16', 'I17', 'I18', 'I19', 'I20', 'I21', 'I22', 'I23', 'I24', 'I25', 'I26', 'I27', 'I28', 'I29', 'I30', 'I31', 'I32', 'I33', 'I34', 'I35', 'I36', 'I37', 'I38', 'J1', 'J2', 'J3', 'J4', 'J5', 'J6', 'J7', 'J8', 'J9', 'J10', 'J11', 'J12', 'J13', 'J14', 'J15', 'J16', 'J17', 'J18', 'J19', 'J20', 'J21', 'J22', 'J23', 'J24', 'J25', 'J26', 'J27', 'J28', 'J29', 'J30', 'J31', 'J32', 'J33', 'J34', 'J35', 'J36', 'J37', 'J38', 'K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K7', 'K8', 'K9', 'K10', 'K11', 'K12', 'K13', 'K14', 'K15', 'K16', 'K17', 'K18', 'K19', 'K20', 'K21', 'K22', 'K23', 'K24', 'K25', 'K26', 'K27', 'K28', 'K29', 'K30', 'K31', 'K32', 'K33', 'K34', 'K35', 'K36', 'K37', 'K38', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9', 'L10', 'L11', 'L12', 'L13', 'L14', 'L15', 'L16', 'L17', 'L18', 'L19', 'L20', 'L21', 'L22', 'L23', 'L24', 'L25', 'L26', 'L27', 'L28', 'L29', 'L30', 'L31', 'L32', 'L33', 'L34', 'L35', 'L36', 'L37', 'L38', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10', 'M11', 'M12', 'M13', 'M14', 'M15', 'M16', 'M17', 'M18', 'M19', 'M20', 'M21', 'M22', 'M23', 'M24', 'M25', 'M26', 'M27', 'M28', 'M29', 'M30', 'M31', 'M32', 'M33', 'M34', 'M35', 'M36', 'M37', 'M38', 'N1', 'N2', 'N3', 'N4', 'N5', 'N6', 'N7', 'N8', 'N9', 'N10', 'N11', 'N12', 'N13', 'N14', 'N15', 'N16', 'N17', 'N18', 'N19', 'N20', 'N21', 'N22', 'N23', 'N24', 'N25', 'N26', 'N27', 'N28', 'N29', 'N30', 'N31', 'N32', 'N33', 'N34', 'N35', 'N36', 'N37', 'N38', 'O1', 'O2', 'O3', 'O4', 'O5', 'O6', 'O7', 'O8', 'O9', 'O10', 'O11', 'O12', 'O13', 'O14', 'O15', 'O16', 'O17', 'O18', 'O19', 'O20', 'O21', 'O22', 'O23', 'O24', 'O25', 'O26', 'O27', 'O28', 'O29', 'O30', 'O31', 'O32', 'O33', 'O34', 'O35', 'O36', 'O37', 'O38', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9', 'P10', 'P11', 'P12', 'P13', 'P14', 'P15', 'P16', 'P17', 'P18', 'P19', 'P20', 'P21', 'P22', 'P23', 'P24', 'P25', 'P26', 'P27', 'P28', 'P29', 'P30', 'P31', 'P32', 'P33', 'P34', 'P35', 'P36', 'P37', 'P38', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8', 'Q9', 'Q10', 'Q11', 'Q12', 'Q13', 'Q14', 'Q15', 'Q16', 'Q17', 'Q18', 'Q19', 'Q20', 'Q21', 'Q22', 'Q23', 'Q24', 'Q25', 'Q26', 'Q27', 'Q28', 'Q29', 'Q30', 'Q31', 'Q32', 'Q33', 'Q34', 'Q35', 'Q36', 'Q37', 'Q38', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'R16', 'R17', 'R18', 'R19', 'R20', 'R21', 'R22', 'R23', 'R24', 'R25', 'R26', 'R27', 'R28', 'R29', 'R30', 'R31', 'R32', 'R33', 'R34', 'R35', 'R36', 'R37', 'R38', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13', 'S14', 'S15', 'S16', 'S17', 'S18', 'S19', 'S20', 'S21', 'S22', 'S23', 'S24', 'S25', 'S26', 'S27', 'S28', 'S29', 'S30', 'S31', 'S32', 'S33', 'S34', 'S35', 'S36', 'S37', 'S38', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12', 'T13', 'T14', 'T15', 'T16', 'T17', 'T18', 'T19', 'T20', 'T21', 'T22', 'T23', 'T24', 'T25', 'T26', 'T27', 'T28', 'T29', 'T30', 'T31', 'T32', 'T33', 'T34', 'T35', 'T36', 'T37', 'T38', 'U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7', 'U8', 'U9', 'U10', 'U11', 'U12', 'U13', 'U14', 'U15', 'U16', 'U17', 'U18', 'U19', 'U20', 'U21', 'U22', 'U23', 'U24', 'U25', 'U26', 'U27', 'U28', 'U29', 'U30', 'U31', 'U32', 'U33', 'U34', 'U35', 'U36', 'U37', 'U38', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8', 'V9', 'V10', 'V11', 'V12', 'V13', 'V14', 'V15', 'V16', 'V17', 'V18', 'V19', 'V20', 'V21', 'V22', 'V23', 'V24', 'V25', 'V26', 'V27', 'V28', 'V29', 'V30', 'V31', 'V32', 'V33', 'V34', 'V35', 'V36', 'V37', 'V38', 'W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8', 'W9', 'W10', 'W11', 'W12', 'W13', 'W14', 'W15', 'W16', 'W17', 'W18', 'W19', 'W20', 'W21', 'W22', 'W23', 'W24', 'W25', 'W26', 'W27', 'W28', 'W29', 'W30', 'W31', 'W32', 'W33', 'W34', 'W35', 'W36', 'W37', 'W38', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'X8', 'X9', 'X10', 'X11', 'X12', 'X13', 'X14', 'X15', 'X16', 'X17', 'X18', 'X19', 'X20', 'X21', 'X22', 'X23', 'X24', 'X25', 'X26', 'X27', 'X28', 'X29', 'X30', 'X31', 'X32', 'X33', 'X34', 'X35', 'X36', 'X37', 'X38', 'Y1', 'Y2', 'Y3', 'Y4', 'Y5', 'Y6', 'Y7', 'Y8', 'Y9', 'Y10', 'Y11', 'Y12', 'Y13', 'Y14', 'Y15', 'Y16', 'Y17', 'Y18', 'Y19', 'Y20', 'Y21', 'Y22', 'Y23', 'Y24', 'Y25', 'Y26', 'Y27', 'Y28', 'Y29', 'Y30', 'Y31', 'Y32', 'Y33', 'Y34', 'Y35', 'Y36', 'Y37', 'Y38', 'Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7', 'Z8'}

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
    return location in valid_parcel_locations


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
        send_json({'status': 'error', 'message': 'Image validation not available (PIL not installed)', 'code': 500})
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
        send_json({'status': 'error', 'message': 'Not authorized', 'code': 401})
        return
    
    # Get POST parameters
    backer_id = form.getfirst('backer-id', '').strip()
    notes = form.getfirst('notes', '').strip()
    
    if not backer_id:
        send_json({'status': 'error', 'message': 'backer-id required', 'code': 400})
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
            
            # Read backer-id and notes from access file
            content = access_file.read_text(encoding='utf-8').strip()
            lines = content.split('\n', 1)
            backer_id = lines[0] if len(lines) > 0 else ''
            notes = lines[1] if len(lines) > 1 else ''
            
            # Check if code has been used (has location file)
            location_file = locations_dir / f'{code}.txt'
            if location_file.exists():
                parcel_location = location_file.read_text(encoding='utf-8').strip()
                status = 'used'
            else:
                parcel_location = None
                status = 'free'
            
            # Build code info
            code_info = {
                'code': code,
                'backer-id': backer_id,
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
    
    # Check if this code has uploaded an image
    location_file = data_dir / 'locations' / f'{code}.txt'
    if not location_file.exists():
        send_json({'status': 'free', 'message': 'no image uploaded'})
        return
    
    # Get the parcel location
    parcel_location = location_file.read_text(encoding='utf-8').strip()
    
    # Return success with parcel location
    send_json({'status': 'success', 'parcel-location': parcel_location})


def handle_get_parcels(form: cgi.FieldStorage, data_dir: Path) -> None:
    """Handle get-parcels command (public).
    
    Returns a list of all parcel locations that have been uploaded.
    No authorization required.
    
    Args:
        form: CGI form data
        data_dir: Path to data directory
    """
    parcels_dir = data_dir / 'parcels'
    
    # Get all parcel files
    parcel_locations = []
    
    if parcels_dir.exists():
        for parcel_file in sorted(parcels_dir.glob('*.png')):
            # Get parcel location from filename (remove .png extension)
            location = parcel_file.stem
            parcel_locations.append(location)
    
    # Return JSON array of parcel locations
    send_json({'status': 'success', 'parcels': parcel_locations})


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
