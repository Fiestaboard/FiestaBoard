#!/usr/bin/env python3
"""
Upscale the master fiesta-icon.png to a high-resolution version (4600x4600px).
Uses Pillow's LANCZOS resampling for the best quality when upscaling.
Targets 4600px so the icon remains above 4000px after any trimming.
"""

import os
from pathlib import Path
from PIL import Image

# Configuration
TARGET_SIZE = 4600

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
MASTER_ICON = PROJECT_ROOT / "fiesta-icon.png"
OUTPUT_FILE = PROJECT_ROOT / "fiesta-icon-4600.png"


def upscale_icon():
    """Upscale the master icon to the target size."""
    # Check if master icon exists
    if not MASTER_ICON.exists():
        raise FileNotFoundError(f"Master icon not found: {MASTER_ICON}")

    # Load master icon
    print(f"Loading master icon from {MASTER_ICON}")
    master_image = Image.open(MASTER_ICON)

    # Ensure it's RGBA (supports transparency)
    if master_image.mode != "RGBA":
        master_image = master_image.convert("RGBA")

    print(f"Original size: {master_image.size[0]}x{master_image.size[1]}")
    print(f"Target size:   {TARGET_SIZE}x{TARGET_SIZE}")

    # Upscale using LANCZOS resampling for best quality
    upscaled = master_image.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)

    # Save the upscaled icon
    upscaled.save(OUTPUT_FILE, "PNG", optimize=True)
    print(f"\n✓ Upscaled icon saved to: {OUTPUT_FILE}")
    print(f"  Size: {upscaled.size[0]}x{upscaled.size[1]}")

    # Verify file size
    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"  File size: {file_size_mb:.1f} MB")


if __name__ == "__main__":
    try:
        upscale_icon()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        exit(1)
