#!/usr/bin/env python3
"""
Convert 'CW&T' text in Space Mono font to polygon coordinates
"""

import requests
import io
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
import numpy as np

def download_space_mono():
    """Download Space Mono Regular font from Google Fonts"""
    url = "https://github.com/googlefonts/spacemono/raw/main/fonts/ttf/SpaceMono-Regular.ttf"
    print("Downloading Space Mono font...")
    response = requests.get(url)
    response.raise_for_status()
    return io.BytesIO(response.content)

def bezier_to_points(p0, p1, p2, p3=None, num_points=20):
    """Convert bezier curve to line segments"""
    t = np.linspace(0, 1, num_points)
    
    if p3 is None:  # Quadratic bezier
        points = np.array([
            (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0],
            (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
        ]).T
    else:  # Cubic bezier
        points = np.array([
            (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0],
            (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
        ]).T
    
    return points[1:]  # Skip first point to avoid duplication

def glyph_to_polygons(font, char, x_offset=0):
    """Extract polygons from a glyph"""
    glyph_set = font.getGlyphSet()
    glyph_name = font.getBestCmap()[ord(char)]
    glyph = glyph_set[glyph_name]
    
    pen = RecordingPen()
    glyph.draw(pen)
    
    contours = []
    current_contour = []
    current_point = None
    
    for command, args in pen.value:
        if command == 'moveTo':
            if current_contour:
                contours.append(current_contour)
            current_point = (args[0][0] + x_offset, args[0][1])
            current_contour = [current_point]
            
        elif command == 'lineTo':
            current_point = (args[0][0] + x_offset, args[0][1])
            current_contour.append(current_point)
            
        elif command == 'qCurveTo':
            # Quadratic bezier curve
            for i in range(len(args) - 1):
                p1 = (args[i][0] + x_offset, args[i][1])
                p2 = (args[i+1][0] + x_offset, args[i+1][1])
                points = bezier_to_points(current_point, p1, p2)
                current_contour.extend(points)
                current_point = p2
                
        elif command == 'curveTo':
            # Cubic bezier curve
            p1 = (args[0][0] + x_offset, args[0][1])
            p2 = (args[1][0] + x_offset, args[1][1])
            p3 = (args[2][0] + x_offset, args[2][1])
            points = bezier_to_points(current_point, p1, p2, p3)
            current_contour.extend(points)
            current_point = p3
            
        elif command == 'closePath':
            if current_contour:
                contours.append(current_contour)
            current_contour = []
    
    if current_contour:
        contours.append(current_contour)
    
    return contours, glyph.width

def scale_to_latlng(polygons, target_width=10, center_lat=39, center_lng=-105):
    """Scale font coordinates to lat/lng coordinates"""
    # Find bounds
    all_points = [p for poly in polygons for p in poly]
    if not all_points:
        return []
    
    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    width = max_x - min_x
    height = max_y - min_y
    
    # Scale to target width while maintaining aspect ratio
    scale = target_width / width if width > 0 else 1
    
    # Transform coordinates
    scaled_polygons = []
    for poly in polygons:
        scaled_poly = []
        for x, y in poly:
            # Normalize to 0-1, scale, center, flip Y (font coords are bottom-up)
            norm_x = (x - min_x) / width if width > 0 else 0
            norm_y = (y - min_y) / height if height > 0 else 0
            
            lng = center_lng + (norm_x - 0.5) * target_width
            lat = center_lat + (0.5 - norm_y) * (height / width * target_width)  # Flip Y
            
            scaled_poly.append([lat, lng])
        scaled_polygons.append(scaled_poly)
    
    return scaled_polygons

def main():
    # Download font
    font_data = download_space_mono()
    font = TTFont(font_data)
    
    # Convert each character
    text = "CW&T"
    all_polygons = []
    x_offset = 0
    
    print(f"Converting '{text}' to polygons...")
    
    for char in text:
        contours, width = glyph_to_polygons(font, char, x_offset)
        all_polygons.extend(contours)
        x_offset += width
    
    # Scale to lat/lng coordinates
    latlng_polygons = scale_to_latlng(all_polygons)
    
    # Format output
    print("\nvar latlngs = [")
    for i, poly in enumerate(latlng_polygons):
        print("  [", end="")
        for j, point in enumerate(poly):
            if j > 0 and j % 3 == 0:
                print("\n   ", end="")
            print(f"[{point[0]:.5f}, {point[1]:.5f}]", end="")
            if j < len(poly) - 1:
                print(", ", end="")
        print("]", end="")
        if i < len(latlng_polygons) - 1:
            print(",")
        else:
            print()
    print("];")
    
    print(f"\nGenerated {len(latlng_polygons)} polygons with {sum(len(p) for p in latlng_polygons)} total points")

if __name__ == "__main__":
    main()
