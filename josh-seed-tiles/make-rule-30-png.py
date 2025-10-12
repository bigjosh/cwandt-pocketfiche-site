# Prompt:
# write a python program that generates the first 1000 rows of wolfram rule 30, and then Extracts 
# the center 500 cols from the bottom 500 rows into a 500x500x1 png

import numpy as np
from PIL import Image

def apply_rule_30(cells):
    """Apply Rule 30 to generate the next row of cells."""
    n = len(cells)
    new_cells = np.zeros(n, dtype=np.uint8)
    
    for i in range(n):
        left = cells[i - 1] if i > 0 else 0
        center = cells[i]
        right = cells[i + 1] if i < n - 1 else 0
        
        # Rule 30: 00011110 in binary
        # Pattern: 111 110 101 100 011 010 001 000
        # Output:   0   0   0   1   1   1   1   0
        pattern = (left << 2) | (center << 1) | right
        new_cells[i] = (30 >> pattern) & 1
    
    return new_cells

def generate_rule_30(rows=1000, width=2000):
    """Generate the specified number of rows of Rule 30."""
    # Initialize the grid
    grid = np.zeros((rows, width), dtype=np.uint8)
    
    # Start with a single cell in the center
    grid[0, width // 2] = 1
    
    # Generate each subsequent row
    for i in range(1, rows):
        grid[i] = apply_rule_30(grid[i - 1])
    
    return grid

def extract_and_save_png(grid, output_filename='rule30.png'):
    """Extract center 500x500 from bottom 500 rows and save as PNG."""
    rows, width = grid.shape
    
    # Extract bottom 500 rows
    bottom_500 = grid[rows - 500:rows, :]
    
    # Extract center 500 columns
    center_col = width // 2
    start_col = center_col - 250
    end_col = center_col + 250
    
    extracted = bottom_500[:, start_col:end_col]
    
    # Convert to 0-255 range (0 stays 0, 1 becomes 255)
    image_data = (extracted * 255).astype(np.uint8)
    
    # Create and save the image
    img = Image.fromarray(image_data, mode='L')
    img.save(output_filename)
    print(f"Saved {extracted.shape[0]}x{extracted.shape[1]} image to {output_filename}")

if __name__ == "__main__":
    print("Generating Rule 30 cellular automaton (1000 rows)...")
    grid = generate_rule_30(rows=1000, width=2000)
    
    print("Extracting center 500x500 region from bottom 500 rows...")
    extract_and_save_png(grid, 'rule30.png')
    print("Done!")