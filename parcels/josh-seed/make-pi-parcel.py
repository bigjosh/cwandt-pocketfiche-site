from PIL import Image
import mpmath

# Written entirely by Claude Sonnet 4.5 with this these prompts (i did not need to edit it at all):

# the goal is to create a 500x500 pixel monochrome PNG file that contains as many legible digits of 
# pi as possible. I can run python programs locally.

# those digits are not readable! lets switch to a 6 pixel tall font, 1 pixel wide for the chars "1" 
# and "." and 3 pixels wide for all others. a single pixel space between adjecent lines and letters.

# Set precision high enough to get many digits
mpmath.mp.dps = 50000

# Get pi digits as string (keep the decimal point)
pi_str = str(mpmath.pi)

# Image settings
img_size = 500
img = Image.new('1', (img_size, img_size), 1)  # monochrome, white background
pixels = img.load()

# Custom 6-pixel tall bitmap font (3 pixels wide, except 1 and . which are 1 pixel wide)
# Each digit is represented as a list of rows (top to bottom)
# 1 = black pixel, 0 = white pixel
font = {
    '0': [
        [1,1,1],
        [1,0,1],
        [1,0,1],
        [1,0,1],
        [1,0,1],
        [1,1,1]
    ],
    '1': [
        [1],
        [1],
        [1],
        [1],
        [1],
        [1]
    ],
    '2': [
        [1,1,1],
        [0,0,1],
        [1,1,1],
        [1,0,0],
        [1,0,0],
        [1,1,1]
    ],
    '3': [
        [1,1,1],
        [0,0,1],
        [1,1,1],
        [0,0,1],
        [0,0,1],
        [1,1,1]
    ],
    '4': [
        [1,0,1],
        [1,0,1],
        [1,1,1],
        [0,0,1],
        [0,0,1],
        [0,0,1]
    ],
    '5': [
        [1,1,1],
        [1,0,0],
        [1,1,1],
        [0,0,1],
        [0,0,1],
        [1,1,1]
    ],
    '6': [
        [1,1,1],
        [1,0,0],
        [1,1,1],
        [1,0,1],
        [1,0,1],
        [1,1,1]
    ],
    '7': [
        [1,1,1],
        [0,0,1],
        [0,0,1],
        [0,0,1],
        [0,0,1],
        [0,0,1]
    ],
    '8': [
        [1,1,1],
        [1,0,1],
        [1,1,1],
        [1,0,1],
        [1,0,1],
        [1,1,1]
    ],
    '9': [
        [1,1,1],
        [1,0,1],
        [1,1,1],
        [0,0,1],
        [0,0,1],
        [1,1,1]
    ],
    '.': [
        [0],
        [0],
        [0],
        [0],
        [0],
        [1]
    ]
}

def draw_char(img, x, y, char):
    """Draw a character at position (x, y) and return the width used"""
    if char not in font:
        return 0
    
    bitmap = font[char]
    width = len(bitmap[0])
    
    for row_idx, row in enumerate(bitmap):
        for col_idx, pixel in enumerate(row):
            px = x + col_idx
            py = y + row_idx
            if px < img_size and py < img_size:
                pixels[px, py] = 1 - pixel  # 0 = black, 1 = white
    
    return width

# Draw digits
x, y = 0, 0
digit_count = 0

for char in pi_str:
    # Check if character fits in current row
    char_width = 1 if char in '1.' else 3
    
    if x + char_width > img_size:
        # Move to next line
        x = 0
        y += 6 + 1  # 6 pixels tall + 1 pixel space
        
        if y + 6 > img_size:
            # Image is full
            break
    
    # Draw the character
    width_used = draw_char(img, x, y, char)
    x += width_used + 1  # Add 1 pixel space after character
    digit_count += 1

print(f"Drew {digit_count} characters (including decimal point)")
print(f"Digits of pi: {digit_count - 1}")  # Subtract 1 for the decimal point

# Save the image
img.save('pi_digits_500x500.png')
print("Saved as pi_digits_500x500.png")

# Print first 100 characters for verification
print(f"\nFirst 100 chars: {pi_str[:100]}")