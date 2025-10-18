#!/usr/bin/env python3
"""
Update access files: replace first line (backer-id) with number from invite_notes if present.
"""

import re
from pathlib import Path


def process_access_file(file_path: Path) -> bool:
    """Process a single access file.
    
    Args:
        file_path: Path to access file
        
    Returns:
        True if file was modified, False otherwise
    """
    # Read the file
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    if len(lines) < 1:
        return False
    
    # Check if last line starts with "invite_notes:" and ends with a number
    last_line = lines[-1].strip()
    
    if not last_line.startswith('invite_notes:'):
        return False
    
    # Extract the part after "invite_notes:"
    invite_notes_value = last_line[len('invite_notes:'):].strip()
    
    # Check if it ends with a number
    match = re.search(r'(\d+)$', invite_notes_value)
    if not match:
        return False
    
    # Extract the number
    number = match.group(1)
    
    # Replace first line with the number
    lines[0] = number
    
    # Write back to file
    new_content = '\n'.join(lines)
    file_path.write_text(new_content, encoding='utf-8')
    
    return True


def main():
    access_dir = Path('D:/Github/cwandt-pocketfiche-site/testing-data-dir/access')
    
    if not access_dir.exists():
        print(f"ERROR: Directory does not exist: {access_dir}")
        return
    
    print(f"Processing files in: {access_dir}\n")
    
    modified_count = 0
    skipped_count = 0
    
    # Process all .txt files in the access directory
    for file_path in sorted(access_dir.glob('*.txt')):
        if process_access_file(file_path):
            print(f"✓ Modified: {file_path.name}")
            modified_count += 1
        else:
            skipped_count += 1
    
    print(f"\n{'='*60}")
    print(f"Complete: {modified_count} modified, {skipped_count} skipped")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
