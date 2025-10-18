#!/usr/bin/env python3
"""
Debug CGI script to test stdin reading and diagnose truncation issues.
"""

import sys
import os
import io
import cgi

def main():
    """Test different methods of reading stdin."""
    
    # Send HTTP headers
    print("Content-Type: text/plain; charset=utf-8\r")
    print("\r")
    
    # Get environment info
    content_length_str = os.environ.get('CONTENT_LENGTH', 'NOT SET')
    content_type = os.environ.get('CONTENT_TYPE', 'NOT SET')
    request_method = os.environ.get('REQUEST_METHOD', 'NOT SET')
    
    print("="*60)
    print("STDIN READING DEBUG TEST")
    print("="*60)
    print()
    print(f"REQUEST_METHOD: {request_method}")
    print(f"CONTENT_TYPE: {content_type}")
    print(f"CONTENT_LENGTH: {content_length_str}")
    print()
    
    if content_length_str == 'NOT SET' or not content_length_str.isdigit():
        print("ERROR: CONTENT_LENGTH not set or invalid")
        return
    
    expected_bytes = int(content_length_str)
    print(f"Expected bytes to read: {expected_bytes}")
    print()
    
    # Test 1: Read exact CONTENT_LENGTH from stdin
    print("="*60)
    print("TEST 1: Read exact CONTENT_LENGTH from stdin.buffer")
    print("="*60)
    try:
        stdin_data = sys.stdin.buffer.read(expected_bytes)
        print(f"Bytes read: {len(stdin_data)}")
        match_result = "YES - COMPLETE" if len(stdin_data) == expected_bytes else "NO - TRUNCATED"
        print(f"Match: {match_result}")
        print()
        
        # Test 2: Parse with cgi.FieldStorage using our buffer
        print("="*60)
        print("TEST 2: Parse with cgi.FieldStorage from buffer")
        print("="*60)
        
        stdin_buffer = io.BytesIO(stdin_data)
        form = cgi.FieldStorage(fp=stdin_buffer, environ=os.environ)
        
        print(f"Form fields: {list(form.keys())}")
        print()
        
        # Check if image field exists
        if 'image' in form:
            file_item = form['image']
            if file_item.file:
                # Read the image data
                image_chunks = []
                while True:
                    chunk = file_item.file.read(8192)
                    if not chunk:
                        break
                    image_chunks.append(chunk)
                
                image_data = b''.join(image_chunks)
                
                print(f"Image field found!")
                print(f"  Filename: {file_item.filename}")
                print(f"  Content-Type: {file_item.type}")
                print(f"  Image data size: {len(image_data)} bytes")
                print(f"  Number of chunks read: {len(image_chunks)}")
                
                if len(image_chunks) > 0:
                    print(f"  First chunk size: {len(image_chunks[0])} bytes")
                    print(f"  Last chunk size: {len(image_chunks[-1])} bytes")
            else:
                print("Image field has no file data")
        else:
            print("No 'image' field found in form")
        
        print()
        print("="*60)
        print("TEST COMPLETE")
        print("="*60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("Content-Type: text/plain; charset=utf-8\r")
        print("\r")
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
