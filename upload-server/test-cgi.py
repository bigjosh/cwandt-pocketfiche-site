#!/usr/bin/env python3
"""Test CGI script to see exact output"""

import os
import sys
import subprocess
from pathlib import Path

# Set up environment
script_dir = Path(__file__).parent
data_dir = script_dir / 'data'

# Ensure data directory exists
data_dir.mkdir(exist_ok=True)
(data_dir / 'admins').mkdir(exist_ok=True)
(data_dir / 'access').mkdir(exist_ok=True)
(data_dir / 'locations').mkdir(exist_ok=True)
(data_dir / 'parcels').mkdir(exist_ok=True)

# Create a test admin
admin_file = data_dir / 'admins' / 'test-admin.txt'
admin_file.write_text('Test Admin\nTest notes')

# Set environment variables
env = os.environ.copy()
env['PF_DATA_DIR'] = str(data_dir.absolute())
env['REQUEST_METHOD'] = 'GET'
env['QUERY_STRING'] = 'command=get-codes&admin-id=test-admin'

print("=" * 60)
print("Testing with valid request (should work):")
print("=" * 60)

# Run the CGI script
result = subprocess.run(
    [sys.executable, 'cgi-bin/app.py'],
    cwd=str(script_dir),
    env=env,
    capture_output=True,
    text=True
)

print("STDOUT:")
print(repr(result.stdout))
print("\nSTDERR:")
print(repr(result.stderr))
print("\nReturn code:", result.returncode)

print("\n" + "=" * 60)
print("Testing with invalid admin (should error with 401):")
print("=" * 60)

# Test with bad auth
env['QUERY_STRING'] = 'command=get-codes&admin-id=invalid-admin'

result = subprocess.run(
    [sys.executable, 'cgi-bin/app.py'],
    cwd=str(script_dir),
    env=env,
    capture_output=True,
    text=True
)

print("STDOUT:")
print(repr(result.stdout))
print("\nSTDERR:")
print(repr(result.stderr))
print("\nReturn code:", result.returncode)

print("\n" + "=" * 60)
print("Testing with unknown command (should error with 400):")
print("=" * 60)

# Test with unknown command
env['QUERY_STRING'] = 'command=invalid-command&admin-id=test-admin'

result = subprocess.run(
    [sys.executable, 'cgi-bin/app.py'],
    cwd=str(script_dir),
    env=env,
    capture_output=True,
    text=True
)

print("STDOUT:")
print(repr(result.stdout))
print("\nSTDERR:")
print(repr(result.stderr))
print("\nReturn code:", result.returncode)
