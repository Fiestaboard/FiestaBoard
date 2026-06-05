#!/usr/bin/env python3
"""Generate screenshot images for all Sun Art stages.

This script generates visual representations of each sun art stage
and saves them as PNG images in the plugin's docs directory.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import importlib.util  # noqa: E402  (must follow sys.path setup above)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

# Load the plugin module
plugin_path = project_root / "plugins" / "sun_art" / "__init__.py"
spec = importlib.util.spec_from_file_location("sun_art_plugin", plugin_path)
sun_art_module = importlib.util.module_from_spec(spec)
sys.modules["sun_art_plugin"] = sun_art_module
spec.loader.exec_module(sun_art_module)
SunArtPlugin = sun_art_module.SunArtPlugin

# Load manifest
manifest_path = project_root / "plugins" / "sun_art" / "manifest.json"
with manifest_path.open() as f:
    manifest = json.load(f)

from src.board_chars import BoardChars  # noqa: E402  (depends on sys.path setup above)

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
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


# Character code to character mapping
def code_to_char(code: int) -> str:
    """Convert character code to character."""
    if 1 <= code <= 26:
        return chr(ord("A") + code - 1)
    if 27 <= code <= 35:
        return str(code - 26)
    if code == 36:
        return "0"
    return " "


# Stage configurations: (stage_name, description)
# 11 stages showing sun rising line-by-line then setting line-by-line
STAGES = [
    ("night", "Night - Black sky with white stars"),
    ("late_night", "Late Night - Stars with faint glow at horizon"),
    ("dawn", "Dawn - Purple sky, orange glow, sun approaching"),
    ("early_sunrise", "Early Sunrise - Sun peeking (1 row)"),
    ("sunrise", "Sunrise - Sun rising (3 rows), blue sky appearing"),
    ("morning", "Morning - Sun high (5 rows), blue sky"),
    ("noon", "Noon - Full sun (6 rows), brightest with white core"),
    ("afternoon", "Afternoon - Sun lowering (5 rows)"),
    ("sunset", "Sunset - Sun setting (3 rows), orange/red sky"),
    ("late_sunset", "Late Sunset - Sun almost gone (2 rows)"),
    ("dusk", "Dusk - Sun just set, red fading to purple"),
    ("twilight", "Twilight - Fading to night, stars appearing"),
]


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
    img = Image.new("RGB", (width, height), color=hex_to_rgb("#0d0d0d"))
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

                # Draw rounded rectangle for color tile
                # PIL doesn't have rounded rectangles, so we'll use a workaround
                # Create a mask for rounded corners

                # Draw the color tile rectangle
                draw.rectangle(
                    [color_x, color_y, color_x + color_w - 1, color_y + color_h - 1], fill=color_rgb, outline=None
                )

                # Add subtle shadow effect (darker edges)
                # Top highlight
                draw.rectangle(
                    [color_x, color_y, color_x + color_w - 1, color_y + 1],
                    fill=tuple(min(255, c + 30) for c in color_rgb),
                )
                # Left highlight
                draw.rectangle(
                    [color_x, color_y, color_x + 1, color_y + color_h - 1],
                    fill=tuple(min(255, c + 20) for c in color_rgb),
                )
                # Bottom shadow
                draw.rectangle(
                    [color_x, color_y + color_h - 2, color_x + color_w - 1, color_y + color_h - 1],
                    fill=tuple(max(0, c - 40) for c in color_rgb),
                )
                # Right shadow
                draw.rectangle(
                    [color_x + color_w - 2, color_y, color_x + color_w - 1, color_y + color_h - 1],
                    fill=tuple(max(0, c - 30) for c in color_rgb),
                )

                # Center line (split-flap effect)
                center_y = color_y + color_h // 2
                draw.rectangle(
                    [color_x, center_y, color_x + color_w - 1, center_y], fill=tuple(max(0, c - 20) for c in color_rgb)
                )

            elif code == BoardChars.SPACE:
                # Space - just leave as background
                pass
            else:
                # Character tile - use dark background with light text
                bg_color = hex_to_rgb("#0d0d0d")

                # Draw tile background
                draw.rectangle([x, y, x + tile_size - 1, y + tile_size - 1], fill=bg_color, outline=None)

                # Draw the character
                char = code_to_char(code)
                # Try to use a monospace font
                try:
                    # Try different font paths
                    font_paths = [
                        "/System/Library/Fonts/Menlo.ttc",
                        "/System/Library/Fonts/Monaco.dfont",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                        "/System/Library/Fonts/Helvetica.ttc",
                    ]
                    font = None
                    for path in font_paths:
                        try:
                            font = ImageFont.truetype(path, size=int(tile_size * 0.6))
                            break
                        except Exception:
                            continue
                    if font is None:
                        font = ImageFont.load_default()
                except Exception:
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


def generate_stage_image(stage_name: str, output_path: Path):
    """Generate an image for a specific stage.

    Directly generates the pattern for the given stage name,
    bypassing elevation calculations (patterns are hardcoded).

    Args:
        stage_name: Name of the stage (e.g., "night", "dawn", "noon")
        output_path: Path to save the image
    """
    print(f"Generating {stage_name} stage image...")

    # Create plugin instance with manifest
    plugin = SunArtPlugin(manifest)

    # Configure plugin minimally (we won't use fetch_data)
    plugin._config = {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "refresh_seconds": 300,
    }
    plugin._enabled = True

    # Directly call _generate_pattern with the stage name
    # This bypasses elevation calculation and uses the hardcoded patterns
    pattern_array = plugin._generate_pattern(stage_name, elevation=0)

    if not pattern_array:
        print(f"  ERROR: No pattern generated for stage '{stage_name}'")
        return False

    # Verify pattern dimensions
    if len(pattern_array) != 6 or any(len(row) != 22 for row in pattern_array):
        print(f"  ERROR: Invalid pattern dimensions for stage '{stage_name}'")
        return False

    # Render the pattern with larger tiles for better quality
    img = render_pattern(pattern_array, tile_size=35, gap=3)

    # Add padding around the board (matching web UI bezel style)
    padding = 30
    final_width = img.width + padding * 2
    final_height = img.height + padding * 2

    # Create final image with dark bezel background (#050505 from web UI)
    final_img = Image.new("RGB", (final_width, final_height), color=hex_to_rgb("#050505"))
    final_img.paste(img, (padding, padding))

    # Save image (no title - cleaner look matching web UI)
    final_img.save(output_path, "PNG", optimize=True)
    print(f"  Saved to {output_path}")
    return True


def main():
    """Generate all stage images."""
    # Output directory
    docs_dir = project_root / "plugins" / "sun_art" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    print("Generating Sun Art stage images...")
    print(f"Output directory: {docs_dir}")
    print(f"Total stages: {len(STAGES)}\n")

    success_count = 0
    for stage_name, _description in STAGES:
        output_path = docs_dir / f"sun-art-{stage_name.replace('_', '-')}.png"
        if generate_stage_image(stage_name, output_path):
            success_count += 1
        print()

    print(f"Generated {success_count}/{len(STAGES)} images successfully")

    if success_count == len(STAGES):
        print("\nAll images generated successfully!")
        return 0
    print("\nSome images failed to generate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
