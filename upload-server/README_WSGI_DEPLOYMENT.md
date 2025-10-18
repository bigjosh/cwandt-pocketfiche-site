# Waitress WSGI Deployment Guide

This guide explains how to migrate from CGI to Waitress WSGI server to fix upload truncation issues.

## Why Waitress?

The CGI implementation had issues with ARR buffering causing uploaded images to be truncated. Waitress is a production-ready WSGI server that handles uploads properly without truncation.

## Architecture

**Before (CGI):**
```
Browser → IIS → CGI Handler → app.py (CGI script)
```

**After (Waitress):**
```
Browser → IIS → ARR Proxy → Waitress → app_wsgi.py (WSGI app)
```

## Installation Steps

### 1. Install Dependencies

```bash
cd D:\Github\cwandt-pocketfiche-site\upload-server
pip install -r requirements.txt
```

This installs:
- `waitress` - Production WSGI server
- `Pillow` - Image processing
- `werkzeug` - Better multipart form handling

### 2. Configure Data Directory

Edit `start_server.bat` and set your data directory:

```batch
set PF_DATA_DIR=D:\Github\cwandt-pocketfiche-site\testing-data-dir
```

Or set it as a system environment variable.

### 3. Test the Server Locally

```bash
start_server.bat
```

You should see:
```
Starting Waitress WSGI server...
  Host: 127.0.0.1
  Port: 8080
  Threads: 4
  Data directory: D:\Github\cwandt-pocketfiche-site\testing-data-dir
  URL: http://127.0.0.1:8080/
```

Test it works:
```bash
curl "http://localhost:8080/?command=get-parcels"
```

### 4. Configure IIS ARR Proxy

The `web.config` has been updated to proxy requests to Waitress.

**Verify ARR is installed:**
1. Open IIS Manager
2. Select your server
3. Look for "Application Request Routing Cache" icon
4. If missing, install ARR: https://www.iis.net/downloads/microsoft/application-request-routing

**Enable ARR proxy:**
1. Double-click "Application Request Routing Cache"
2. Click "Server Proxy Settings" in right panel
3. Check "Enable proxy"
4. Click "Apply"

### 5. Start Waitress as a Windows Service (Production)

For production, you should run Waitress as a Windows Service so it starts automatically.

**Option A: Using NSSM (Non-Sucking Service Manager)**

1. Download NSSM: https://nssm.cc/download
2. Extract `nssm.exe`
3. Run as administrator:
   ```cmd
   nssm install PocketFicheUpload
   ```
4. Configure:
   - Path: `C:\Python\python.exe` (your Python path)
   - Startup directory: `D:\Github\cwandt-pocketfiche-site\upload-server`
   - Arguments: `server.py`
   - Environment: Add `PF_DATA_DIR=D:\Github\cwandt-pocketfiche-site\testing-data-dir`
5. Start the service:
   ```cmd
   nssm start PocketFicheUpload
   ```

**Option B: Using Task Scheduler**

1. Open Task Scheduler
2. Create Basic Task
3. Name: "Pocket Fiche Upload Server"
4. Trigger: "When computer starts"
5. Action: "Start a program"
   - Program: `D:\Github\cwandt-pocketfiche-site\upload-server\start_server.bat`
6. Settings: Check "Run whether user is logged on or not"

### 6. Verify Everything Works

**Test through IIS:**
```bash
# From your domain
curl "https://yourdomain.com/cgi-bin/app.py?command=get-parcels"
```

**Test file upload:**
Use the upload.html interface and check the browser console for any errors.

## Configuration

### Environment Variables

- `PF_DATA_DIR` - **Required**. Path to data directory
- `WSGI_HOST` - Optional. Default: `127.0.0.1`
- `WSGI_PORT` - Optional. Default: `8080`
- `WSGI_THREADS` - Optional. Default: `4`

### Waitress Settings

Edit `server.py` to change:
- `channel_timeout` - Max time for request (default: 300 seconds)
- `recv_bytes` - Receive buffer size (default: 64KB)
- `send_bytes` - Send buffer size (default: 64KB)
- `threads` - Number of worker threads (default: 4)

## Troubleshooting

### Server won't start

**Error:** `PF_DATA_DIR environment variable not set`
- Solution: Set the environment variable in `start_server.bat` or system settings

**Error:** `Address already in use`
- Solution: Port 8080 is already taken. Change `WSGI_PORT` in `start_server.bat`

### Uploads still truncated

**Check ARR proxy is working:**
1. IIS Manager → Your site → URL Rewrite
2. Verify "Proxy to Waitress WSGI" rule exists
3. Test the rule with "Test Pattern" feature

**Check Waitress logs:**
- Look at console output from `server.py`
- Check for DEBUG messages about received bytes

### 502 Bad Gateway

- Waitress server is not running
- Port mismatch between web.config and server
- Firewall blocking localhost:8080

Solution: Ensure Waitress is running and accessible:
```bash
curl http://localhost:8080/?command=get-parcels
```

## Monitoring

**View Waitress logs:**
- If running from `start_server.bat`, logs appear in console
- If running as service, redirect to file in `server.py`:
  ```python
  sys.stdout = open('waitress.log', 'a')
  sys.stderr = open('waitress_errors.log', 'a')
  ```

**Health check endpoint:**
```bash
curl "http://localhost:8080/?command=get-parcels"
```

Should return: `{"status":"success","parcels":[...]}`

## Rollback to CGI

If you need to rollback to CGI:

1. Stop Waitress service
2. Restore old `web.config` (remove rewrite rules)
3. Use `cgi-bin/app.py` (old CGI version)

## Performance

Waitress default settings should handle:
- 4 concurrent requests (4 threads)
- 50MB max upload size
- 5 minute timeout for slow uploads

For higher load, increase threads in `server.py`:
```python
threads=8  # or more
```

## Security Notes

- Waitress runs on `localhost:8080` only (not exposed to internet)
- IIS/ARR provides the public interface with HTTPS
- All authentication is maintained in WSGI app
- File operations remain atomic

## Migration Checklist

- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Set `PF_DATA_DIR` in `start_server.bat`
- [ ] Test Waitress locally (`start_server.bat`)
- [ ] Verify ARR is installed and enabled in IIS
- [ ] Deploy updated `web.config`
- [ ] Set up Waitress as Windows Service
- [ ] Test upload through IIS
- [ ] Monitor for 24 hours
- [ ] Remove old CGI files (optional)

## Files Reference

- `app_wsgi.py` - WSGI application (new)
- `server.py` - Waitress startup script (new)
- `start_server.bat` - Windows startup script (new)
- `requirements.txt` - Python dependencies (new)
- `web.config` - IIS configuration (updated)
- `app.py` - Old CGI script (keep as backup)

## Support

For issues, check:
1. Waitress console output
2. IIS logs: `C:\inetpub\logs\LogFiles`
3. Windows Event Viewer → Application logs
