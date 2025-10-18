#!/usr/bin/env python3
"""
Waitress WSGI server startup script for Pocket Fische Upload Server.

This starts a production-ready WSGI server that handles the upload API.
IIS/ARR will proxy requests to this server.
"""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from waitress import serve
from app import application


def main():
    """Start the Waitress server."""
    # Configuration
    host = os.environ.get('WSGI_HOST', '127.0.0.1')
    port = int(os.environ.get('WSGI_PORT', '8000'))
    threads = int(os.environ.get('WSGI_THREADS', '4'))
    
    # Check for data directory
    data_dir = os.environ.get('PF_DATA_DIR', '')
    if not data_dir:
        print("ERROR: PF_DATA_DIR environment variable not set", file=sys.stderr)
        print("Please set it to the path of your data directory", file=sys.stderr)
        sys.exit(1)
    
    if not Path(data_dir).exists():
        print(f"ERROR: Data directory does not exist: {data_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Starting Waitress WSGI server...")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Threads: {threads}")
    print(f"  Data directory: {data_dir}")
    print(f"  URL: http://{host}:{port}/")
    print()
    print("Press Ctrl+C to stop the server")
    print()
    
    # Start server
    serve(
        application,
        host=host,
        port=port,
        threads=threads,
        url_scheme='http',
        ident='PocketFische/1.0',
        # Connection settings
        channel_timeout=300,  # 5 minutes for slow uploads
        # Buffer settings - important for large uploads
        recv_bytes=65536,  # 64KB receive buffer
        send_bytes=65536,  # 64KB send buffer
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        sys.exit(0)
