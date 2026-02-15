#!/usr/bin/env python3
"""Generate screenshot image for Last.fm Now Playing plugin.

This script generates a visual representation of the Last.fm plugin
displaying a "Now Playing" track on the Vestaboard and saves it as a PNG.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image, ImageDraw, ImageFont
from src.board_chars import BoardChars
from src.text_to_board import text_to_board_array

# Official FiestaBoard color hex values (from web/src/lib/board-colors.ts)
COLOR_HEX = {
    BoardChars.RED: "#eb4034",
    BoardChars.ORANGE: "#f5a623",
    BoardChars.YELLOW: "#f8e71c",
    BoardChars.GREEN: "#7ed321",
    BoardChars.BLUE: "#4a90d9",
    BoardChars.VIOLET: "#9b59b6",
    BoardChars.WHITE: "#ffffff",
    BoardChars.BLACK: "#1a1a1a",
    BoardChars.SPACE: "#0d0d0d",  # Dark background for space
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
    """Render a pattern array as an image matching the web UI style.
    
    Args:
        pattern_array: 6x22 array of character codes
        tile_size: Size of each tile in pixels
        gap: Gap between tiles in pixels
        
    Returns:
        PIL Image
    """
    rows = len(pattern_array)
    cols = len(pattern_array[0]) if rows > 0 else 0
    
    # Calculate image dimensions
    width = cols * tile_size + (cols - 1) * gap
    height = rows * tile_size + (rows - 1) * gap
    
    # Create image with dark background matching web UI (#0d0d0d)
    img = Image.new('RGB', (width, height), color=hex_to_rgb("#0d0d0d"))
    draw = ImageDraw.Draw(img)
    
    # Color tile margins (smaller than full tile, like web UI)
    color_margin_top = 3
    color_margin_bottom = 4
    color_margin_h = 1
    
    # Draw each tile
    for row_idx, row in enumerate(pattern_array):
        for col_idx, code in enumerate(row):
            x = col_idx * (tile_size + gap)
            y = row_idx * (tile_size + gap)
            
            # Check if it's a color tile
            if code in COLOR_HEX:
                # Color tile - draw with margins and rounded corners
                hex_color = COLOR_HEX[code]
                color_rgb = hex_to_rgb(hex_color)
                
                # Calculate color tile position (with margins)
                color_x = x + color_margin_h
                color_y = y + color_margin_top
                color_w = tile_size - (color_margin_h * 2)
                color_h = tile_size - (color_margin_top + color_margin_bottom)
                
                # Draw the color tile rectangle
                draw.rectangle(
                    [color_x, color_y, color_x + color_w - 1, color_y + color_h - 1],
                    fill=color_rgb,
                    outline=None
                )
                
                # Add subtle shadow effect (darker edges)
                # Top highlight
                draw.rectangle(
                    [color_x, color_y, color_x + color_w - 1, color_y + 1],
                    fill=tuple(min(255, c + 30) for c in color_rgb)
                )
                # Left highlight
                draw.rectangle(
                    [color_x, color_y, color_x + 1, color_y + color_h - 1],
                    fill=tuple(min(255, c + 20) for c in color_rgb)
                )
                # Bottom shadow
                draw.rectangle(
                    [color_x, color_y + color_h - 2, color_x + color_w - 1, color_y + color_h - 1],
                    fill=tuple(max(0, c - 40) for c in color_rgb)
                )
                # Right shadow
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
                # Space - just leave as background
                pass
            else:
                # Character tile - use dark background with light text
                bg_color = hex_to_rgb("#0d0d0d")
                
                # Draw tile background
                draw.rectangle(
                    [x, y, x + tile_size - 1, y + tile_size - 1],
                    fill=bg_color,
                    outline=None
                )
                
                # Draw the character
                char = code_to_char(code)
                # Try to use a monospace font
                try:
                    # Try different font paths
                    font_paths = [
                        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
                        "/System/Library/Fonts/Menlo.ttc",
                        "/System/Library/Fonts/Monaco.dfont",
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
                
                # Calculate text position (centered)
                if font:
                    bbox = draw.textbbox((0, 0), char, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                else:
                    text_width = tile_size // 2
                    text_height = tile_size // 2
                
                text_x = x + (tile_size - text_width) // 2
                text_y = y + (tile_size - text_height) // 2
                
                # Draw character in light color (#f0f0e8 from web UI)
                draw.text((text_x, text_y), char, fill=hex_to_rgb("#f0f0e8"), font=font)
    
    return img

def generate_lastfm_screenshot(output_path: Path):
    """Generate a screenshot of the Last.fm plugin display.
    
    Creates a sample "Now Playing" display with:
    - NOW PLAYING status
    - Song title
    - Artist name
    
    Args:
        output_path: Path to save the image
    """
    print("Generating Last.fm Now Playing screenshot...")
    
    # Create a sample display matching the plugin's get_formatted_display method
    # Example: "Bohemian Rhapsody" by "Queen"
    display_text = """   NOW PLAYING

 BOHEMIAN RHAPSODY
       QUEEN
"""
    
    # Convert text to board array
    pattern_array = text_to_board_array(display_text, use_color_tiles=False)
    
    # Verify pattern dimensions
    if len(pattern_array) != 6 or any(len(row) != 22 for row in pattern_array):
        print(f"  ERROR: Invalid pattern dimensions")
        return False
    
    # Render the pattern with larger tiles for better quality
    img = render_pattern(pattern_array, tile_size=35, gap=3)
    
    # Add padding around the board (matching web UI bezel style)
    padding = 30
    final_width = img.width + padding * 2
    final_height = img.height + padding * 2
    
    # Create final image with dark bezel background (#050505 from web UI)
    final_img = Image.new('RGB', (final_width, final_height), color=hex_to_rgb("#050505"))
    final_img.paste(img, (padding, padding))
    
    # Save image
    final_img.save(output_path, "PNG", optimize=True)
    print(f"  Saved to {output_path}")
    return True

def main():
    """Generate the Last.fm screenshot."""
    # Output directory
    docs_dir = project_root / "plugins" / "last_fm" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = docs_dir / "last-fm-display.png"
    
    print(f"Generating Last.fm Now Playing screenshot...")
    print(f"Output path: {output_path}\n")
    
    if generate_lastfm_screenshot(output_path):
        print("\nScreenshot generated successfully!")
        return 0
    else:
        print("\nFailed to generate screenshot.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
