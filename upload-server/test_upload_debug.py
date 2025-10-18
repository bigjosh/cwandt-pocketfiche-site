#!/usr/bin/env python3
"""
Debug script to test upload and see exactly how much data we're receiving.
"""

import sys
import os
from pathlib import Path


def test_stdin_reading():
    """Test different methods of reading stdin to see what works."""
    
    print("Content-Type: text/plain; charset=utf-8\r\n\r\n", end='')
    
    # Get environment info
    content_length = os.environ.get('CONTENT_LENGTH', 'NOT SET')
    content_type = os.environ.get('CONTENT_TYPE', 'NOT SET')
    request_method = os.environ.get('REQUEST_METHOD', 'NOT SET')
    
    print(f"CONTENT_LENGTH: {content_length}")
    print(f"CONTENT_TYPE: {content_type}")
    print(f"REQUEST_METHOD: {request_method}")
    print()
    
    if content_length != 'NOT SET':
        expected_bytes = int(content_length)
        print(f"Expected bytes: {expected_bytes}")
        print()
        
        # Method 1: Read all at once
        print("Method 1: sys.stdin.buffer.read()")
        sys.stdin.buffer.seek(0)  # Reset if possible
        data1 = sys.stdin.buffer.read()
        print(f"  Received: {len(data1)} bytes")
        print(f"  Match: {'YES' if len(data1) == expected_bytes else 'NO'}")
        print()
        
        # Method 2: Read in chunks
        print("Method 2: Chunked reading")
        sys.stdin.buffer.seek(0)  # Reset
        chunks = []
        chunk_size = 8192
        while True:
            chunk = sys.stdin.buffer.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
        data2 = b''.join(chunks)
        print(f"  Chunks read: {len(chunks)}")
        print(f"  Received: {len(data2)} bytes")
        print(f"  Match: {'YES' if len(data2) == expected_bytes else 'NO'}")
        print()
        
        # Method 3: Read exact content length
        print("Method 3: Read exact CONTENT_LENGTH")
        sys.stdin.buffer.seek(0)  # Reset
        data3 = sys.stdin.buffer.read(expected_bytes)
        print(f"  Received: {len(data3)} bytes")
        print(f"  Match: {'YES' if len(data3) == expected_bytes else 'NO'}")
        print()


if __name__ == '__main__':
    test_stdin_reading()
