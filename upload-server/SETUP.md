# Pocket Fische Upload Server - Setup Guide

## Overview

This upload server allows:
- **Admins** to generate unique upload codes for backers
- **Backers** to upload their parcel images and choose locations

All files created and ready to use:
- ✅ `cgi-bin/app.py` - Main CGI script handler
- ✅ `style.css` - Shared styles for all pages
- ✅ `admin.html` - Admin interface to generate codes
- ✅ `upload.html` - Backer interface to upload parcels
- ✅ `index.html` - Landing page
- ✅ `cgi-bin/index.html` - Blocks directory listing

## Prerequisites

1. **Python 3.x** installed
2. **Pillow library** for image processing:
   ```bash
   pip install Pillow
   ```

## Setup Steps

### 1. Create Data Directory

Create a data folder **outside** the upload-server directory:

```
# Example on Windows
set PF_DATA_DIR=C:\pocketfiche-data
mkdir %PF_DATA_DIR%
mkdir %PF_DATA_DIR%\admins
mkdir %PF_DATA_DIR%\access
mkdir %PF_DATA_DIR%\locations
mkdir %PF_DATA_DIR%\parcels
```

### 2. Set Environment Variable

Set the `PF_DATA_DIR` environment variable to point to your data directory:

**Windows (Command Prompt):**
```cmd
setx PF_DATA_DIR "C:\pocketfische-data"
```

**Windows (PowerShell):**
```powershell
[Environment]::SetEnvironmentVariable("PF_DATA_DIR", "C:\pocketfische-data", "User")
```

**Linux/Mac:**
```bash
export PF_DATA_DIR="/path/to/pocketfische-data"
# Add to ~/.bashrc or ~/.zshrc to make permanent
```

### 3. Create Admin User(s)

Create admin user files in `{PF_DATA_DIR}/admins/`:

Example: Create file `C:\pocketfische-data\admins\ABCDEFGH.txt` with content:
```
Admin Name
Optional notes about this admin
```

The filename (e.g., `ABCDEFGH.txt`) is the admin-id and acts as the password.
Use a random 8-character uppercase string for security.

### 4. Start the Server

From the `upload-server` directory:

```bash
python -m http.server 8000 --cgi
```

The server will start on http://localhost:8000

### 5. Access the System

**Landing page:**
```
http://localhost:8000/
```

**Admin page (replace ABCDEFGH with your admin-id):**
```
http://localhost:8000/admin.html?admin-id=ABCDEFGH
```

**Upload page (code provided by admin):**
```
http://localhost:8000/upload.html?code=XXXXXXXX
```

## Usage Workflow

### For Admins

1. Visit `admin.html?admin-id=YOUR_ADMIN_ID`
2. Enter backer ID and optional notes
3. Click "Generate Code"
4. Copy the generated URL and send it to the backer

### For Backers

1. Click the URL provided by admin
2. Drag and drop or select an image file
3. Image is automatically converted to 500x500 1-bit black-and-white PNG
4. Enter desired parcel location (A1 to AL38, uppercase)
5. Click "Upload Image"
6. Success! The parcel is now in the world

## Security Notes

- **Admin-ID**: Acts as password - keep secret
- **Data Directory**: Must be outside web server path
- **Access Codes**: 8 random uppercase letters, cryptographically strong
- **One-time Upload**: Each code can only upload once
- **Location Locking**: Each location can only be claimed once

## Troubleshooting

### "PF_DATA_DIR environment variable not set"
- Make sure you set the PF_DATA_DIR environment variable
- Restart your terminal/command prompt after setting it
- Verify with: `echo %PF_DATA_DIR%` (Windows) or `echo $PF_DATA_DIR` (Linux/Mac)

### "Not authorized" error
- Check that admin-id matches a file in `{PF_DATA_DIR}/admins/`
- Check that the file exists and is readable

### "Image validation not available"
- Install Pillow: `pip install Pillow`

### "Invalid image" error
- Image must be PNG format
- Image must be exactly 500x500 pixels
- Image must be 1-bit black-and-white (mode '1' in PIL)

### CGI script not executing
- Make sure you're running with `--cgi` flag
- Check that app.py has execute permissions (Linux/Mac: `chmod +x cgi-bin/app.py`)
- Verify shebang line is correct: `#!/usr/bin/env python3`

## File Structure

```
upload-server/
├── index.html          # Landing page
├── admin.html          # Admin interface
├── upload.html         # Backer upload interface
├── style.css           # Shared styles
├── cgi-bin/
│   ├── app.py         # Main CGI script
│   └── index.html     # Blocks directory listing
└── SETUP.md           # This file

data/ (outside upload-server)
├── admins/            # Admin credentials
├── access/            # Generated access codes
├── locations/         # Used codes with locations
└── parcels/           # Uploaded parcel images
```

## Production Deployment

For production with HTTPS:

1. Set up IIS, Apache, or nginx as reverse proxy
2. Configure SSL certificates
3. Forward requests to the Python CGI server
4. See `../iis/readme.md` for IIS-specific setup

## Testing

To test the system locally:

1. Create a test admin: `{PF_DATA_DIR}/admins/TESTADMIN.txt`
2. Visit: `http://localhost:8000/admin.html?admin-id=TESTADMIN`
3. Generate a code for test backer
4. Visit the upload URL
5. Upload a test image to location A1

## Support

For issues or questions, refer to the main readme.md in the upload-server directory.
