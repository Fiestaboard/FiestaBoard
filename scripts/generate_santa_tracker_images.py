#!/usr/bin/env python3
"""Generate screenshot images for Santa Tracker plugin.

This script generates visual representations of the Santa Tracker plugin
in different states and saves them as PNG images in the plugin's docs directory.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image, ImageDraw, ImageFont
import importlib.util

# Load the plugin module
plugin_path = project_root / "plugins" / "santa_tracker" / "__init__.py"
spec = importlib.util.spec_from_file_location("santa_tracker_plugin", plugin_path)
santa_tracker_module = importlib.util.module_from_spec(spec)
sys.modules["santa_tracker_plugin"] = santa_tracker_module
spec.loader.exec_module(santa_tracker_module)
SantaTrackerPlugin = santa_tracker_module.SantaTrackerPlugin

# Load manifest
manifest_path = project_root / "plugins" / "santa_tracker" / "manifest.json"
with open(manifest_path, 'r') as f:
    manifest = json.load(f)

from src.board_chars import BoardChars

# Official FiestaBoard color hex values
COLOR_HEX = {
    BoardChars.RED: "#eb4034",
    BoardChars.ORANGE: "#f5a623",
    BoardChars.YELLOW: "#f8e71c",
    BoardChars.GREEN: "#7ed321",
    BoardChars.BLUE: "#4a90d9",
    BoardChars.VIOLET: "#9b59b6",
    BoardChars.WHITE: "#ffffff",
    BoardChars.BLACK: "#1a1a1a",
    BoardChars.SPACE: "#0d0d0d",
}

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def code_to_char(code: int) -> str:
    """Convert character code to character."""
    if 1 <= code <= 26:
        return chr(ord('A') + code - 1)
    elif 27 <= code <= 35:
        return str(code - 26)
    elif code == 36:
        return "0"
    else:
        return " "

def render_pattern(pattern_array, tile_size=40, gap=3):
    """Render a pattern array as an image matching the web UI style."""
    rows = len(pattern_array)
    cols = len(pattern_array[0]) if rows > 0 else 0
    
    # Calculate image dimensions
    width = cols * tile_size + (cols - 1) * gap
    height = rows * tile_size + (rows - 1) * gap
    
    # Create image with dark background
    img = Image.new('RGB', (width, height), color=hex_to_rgb("#0d0d0d"))
    draw = ImageDraw.Draw(img)
    
    # Color tile margins
    color_margin_top = 3
    color_margin_bottom = 4
    color_margin_h = 1
    
    # Draw each tile
    for row_idx, row in enumerate(pattern_array):
        for col_idx, code in enumerate(row):
            x = col_idx * (tile_size + gap)
            y = row_idx * (tile_size + gap)
            
            if code in COLOR_HEX:
                # Color tile
                hex_color = COLOR_HEX[code]
                color_rgb = hex_to_rgb(hex_color)
                
                color_x = x + color_margin_h
                color_y = y + color_margin_top
                color_w = tile_size - (color_margin_h * 2)
                color_h = tile_size - (color_margin_top + color_margin_bottom)
                
                draw.rectangle(
                    [color_x, color_y, color_x + color_w - 1, color_y + color_h - 1],
                    fill=color_rgb,
                    outline=None
                )
                
                # Add subtle shadow effect
                draw.rectangle(
                    [color_x, color_y, color_x + color_w - 1, color_y + 1],
                    fill=tuple(min(255, c + 30) for c in color_rgb)
                )
                draw.rectangle(
                    [color_x, color_y, color_x + 1, color_y + color_h - 1],
                    fill=tuple(min(255, c + 20) for c in color_rgb)
                )
                draw.rectangle(
                    [color_x, color_y + color_h - 2, color_x + color_w - 1, color_y + color_h - 1],
                    fill=tuple(max(0, c - 40) for c in color_rgb)
                )
                draw.rectangle(
                    [color_x + color_w - 2, color_y, color_x + color_w - 1, color_y + color_h - 1],
                    fill=tuple(max(0, c - 30) for c in color_rgb)
                )
                
                # Center line (split-flap effect)
                center_y = color_y + color_h // 2
                draw.rectangle(
                    [color_x, center_y, color_x + color_w - 1, center_y],
                    fill=tuple(max(0, c - 20) for c in color_rgb)
                )
                
            elif code == BoardChars.SPACE:
                pass
            else:
                # Character tile
                bg_color = hex_to_rgb("#0d0d0d")
                
                draw.rectangle(
                    [x, y, x + tile_size - 1, y + tile_size - 1],
                    fill=bg_color,
                    outline=None
                )
                
                # Draw the character
                char = code_to_char(code)
                try:
                    font_paths = [
                        "/System/Library/Fonts/Menlo.ttc",
                        "/System/Library/Fonts/Monaco.dfont",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                        "/System/Library/Fonts/Helvetica.ttc",
                    ]
                    font = None
                    for path in font_paths:
                        try:
                            font = ImageFont.truetype(path, size=int(tile_size * 0.6))
                            break
                        except:
                            continue
                    if font is None:
                        font = ImageFont.load_default()
                except:
                    font = ImageFont.load_default()
                
                if font:
                    bbox = draw.textbbox((0, 0), char, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                else:
                    text_width = tile_size // 2
                    text_height = tile_size // 2
                
                text_x = x + (tile_size - text_width) // 2
                text_y = y + (tile_size - text_height) // 2
                
                draw.text((text_x, text_y), char, fill=hex_to_rgb("#f0f0e8"), font=font)
    
    return img

def create_simple_display(text_lines, tile_size=35, gap=3):
    """Create a simple text display for Santa Tracker states."""
    # Convert text lines to character codes (simple 6x22 grid)
    pattern = []
    for i in range(6):
        if i < len(text_lines):
            line = text_lines[i].upper()[:22].ljust(22)
            row = []
            for char in line:
                if char == ' ':
                    row.append(BoardChars.SPACE)
                elif 'A' <= char <= 'Z':
                    row.append(ord(char) - ord('A') + 1)
                elif '1' <= char <= '9':
                    row.append(ord(char) - ord('1') + 27)
                elif char == '0':
                    row.append(36)
                elif char == '%':
                    row.append(BoardChars.SPACE)  # Use space for special chars
                elif char == ':':
                    row.append(BoardChars.SPACE)
                elif char == ',':
                    row.append(BoardChars.SPACE)
                elif char == '!':
                    row.append(BoardChars.SPACE)
                else:
                    row.append(BoardChars.SPACE)
            pattern.append(row)
        else:
            pattern.append([BoardChars.SPACE] * 22)
    
    return render_pattern(pattern, tile_size, gap)

def generate_screenshot(scenario: str, output_path: Path):
    """Generate a screenshot for a specific scenario."""
    print(f"Generating {scenario} screenshot...")
    
    if scenario == "before-christmas":
        # Before Christmas state
        lines = [
            "                      ",
            " SANTA IS GETTING    ",
            " READY FOR 2026      ",
            "                      ",
            " LOCATION NORTH POLE ",
            "                      ",
        ]
    elif scenario == "during-delivery":
        # During delivery state
        lines = [
            " SANTA IS DELIVERING ",
            " PRESENTS             ",
            " AT PARIS FRANCE      ",
            " NEXT NEW YORK USA    ",
            " PROGRESS 52          ",
            "                      ",
        ]
    elif scenario == "after-christmas":
        # After Christmas state
        lines = [
            "                      ",
            " SANTA IS DONE FOR   ",
            " 2026                 ",
            "                      ",
            "                      ",
            "                      ",
        ]
    elif scenario == "in-action":
        # Main display showing active delivery
        lines = [
            " SANTA IS DELIVERING ",
            " PRESENTS             ",
            "                      ",
            " CURRENT TOKYO JAPAN  ",
            " PROGRESS 38          ",
            "                      ",
        ]
    elif scenario == "display":
        # General display showing plugin output
        lines = [
            " SANTA TRACKER        ",
            "                      ",
            " SANTA IS DELIVERING ",
            " PRESENTS             ",
            " AT LONDON ENGLAND    ",
            " PROGRESS 57          ",
        ]
    else:
        print(f"  ERROR: Unknown scenario '{scenario}'")
        return False
    
    # Create the image
    img = create_simple_display(lines, tile_size=35, gap=3)
    
    # Add padding (bezel)
    padding = 30
    final_width = img.width + padding * 2
    final_height = img.height + padding * 2
    
    final_img = Image.new('RGB', (final_width, final_height), color=hex_to_rgb("#050505"))
    final_img.paste(img, (padding, padding))
    
    # Save image
    final_img.save(output_path, "PNG", optimize=True)
    print(f"  Saved to {output_path}")
    return True

def main():
    """Generate all Santa Tracker screenshots."""
    docs_dir = project_root / "plugins" / "santa_tracker" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    print("Generating Santa Tracker screenshots...")
    print(f"Output directory: {docs_dir}\n")
    
    scenarios = [
        ("display", "santa-tracker-display.png"),
        ("in-action", "santa-tracker-in-action.png"),
        ("before-christmas", "santa-before-christmas.png"),
        ("during-delivery", "santa-during-delivery.png"),
        ("after-christmas", "santa-after-christmas.png"),
    ]
    
    success_count = 0
    for scenario, filename in scenarios:
        output_path = docs_dir / filename
        if generate_screenshot(scenario, output_path):
            success_count += 1
        print()
    
    print(f"Generated {success_count}/{len(scenarios)} images successfully")
    
    if success_count == len(scenarios):
        print("\nAll images generated successfully!")
        return 0
    else:
        print("\nSome images failed to generate.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
