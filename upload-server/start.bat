@echo off
REM Startup script for Waitress WSGI server (Windows)

REM Optional: Configure host/port
REM set WSGI_HOST=127.0.0.1
REM set WSGI_PORT=8080
REM set WSGI_THREADS=4

REM Start the server
echo Starting Pocket Fische Upload Server...
echo Data directory: %PF_DATA_DIR%
echo.

python server.py
