#!/usr/bin/env python3
"""
Generate all required icon sizes from the master fiesta-icon.png file.
This script creates favicons, PWA icons, and app icons for various platforms.
"""

from pathlib import Path

from PIL import Image

# Define all required icon sizes
FAVICON_SIZES = [16, 32, 48]
PWA_SIZES = [72, 96, 128, 144, 152, 180, 192, 384, 512]
APPLE_TOUCH_ICON_SIZE = 180

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
MASTER_ICON = PROJECT_ROOT / "fiesta-icon.png"
OUTPUT_DIR = PROJECT_ROOT / "web" / "public" / "icons"


def generate_icons():
    """Generate all icon sizes from the master icon file."""
    # Check if master icon exists
    if not MASTER_ICON.exists():
        raise FileNotFoundError(f"Master icon not found: {MASTER_ICON}")

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load master icon
    print(f"Loading master icon from {MASTER_ICON}")
    master_image = Image.open(MASTER_ICON)

    # Ensure it's RGBA (supports transparency)
    if master_image.mode != "RGBA":
        master_image = master_image.convert("RGBA")

    print(f"Master icon size: {master_image.size}")
    print(f"Master icon mode: {master_image.mode}")

    # Generate favicon sizes
    print("\nGenerating favicon sizes...")
    for size in FAVICON_SIZES:
        icon = master_image.resize((size, size), Image.Resampling.LANCZOS)
        output_path = OUTPUT_DIR / f"favicon-{size}x{size}.png"
        icon.save(output_path, "PNG", optimize=True)
        print(f"  Created: {output_path}")

    # Generate favicon.ico (multi-size ICO file)
    print("\nGenerating favicon.ico...")
    ico_sizes = [16, 32, 48]
    ico_images = []
    for size in ico_sizes:
        ico_images.append(master_image.resize((size, size), Image.Resampling.LANCZOS))

    ico_path = OUTPUT_DIR / "favicon.ico"
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in ico_sizes],
        append_images=ico_images[1:] if len(ico_images) > 1 else None,
    )
    print(f"  Created: {ico_path}")

    # Generate PWA icon sizes
    print("\nGenerating PWA icon sizes...")
    for size in PWA_SIZES:
        icon = master_image.resize((size, size), Image.Resampling.LANCZOS)
        output_path = OUTPUT_DIR / f"icon-{size}x{size}.png"
        icon.save(output_path, "PNG", optimize=True)
        print(f"  Created: {output_path}")

    # Generate apple-touch-icon
    print("\nGenerating Apple touch icon...")
    apple_icon = master_image.resize((APPLE_TOUCH_ICON_SIZE, APPLE_TOUCH_ICON_SIZE), Image.Resampling.LANCZOS)
    apple_path = OUTPUT_DIR / "apple-touch-icon.png"
    apple_icon.save(apple_path, "PNG", optimize=True)
    print(f"  Created: {apple_path}")

    # Also create a root-level favicon.ico for Next.js
    root_favicon = PROJECT_ROOT / "web" / "public" / "favicon.ico"
    ico_images[0].save(
        root_favicon,
        format="ICO",
        sizes=[(size, size) for size in ico_sizes],
        append_images=ico_images[1:] if len(ico_images) > 1 else None,
    )
    print(f"  Created: {root_favicon}")

    print(f"\n✓ Successfully generated {len(FAVICON_SIZES) + len(PWA_SIZES) + 3} icon files!")
    print(f"  Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        generate_icons()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        exit(1)
