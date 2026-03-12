#!/usr/bin/env python3
"""Export FiestaBoard brand lockup PNGs using Playwright.

Renders scripts/brand-export.html in headless Chromium, screenshots the
light and dark lockup elements at 2x scale with transparent backgrounds.

Usage (from repo root):
    pip install playwright && playwright install chromium  # one-time
    python scripts/export-brand-assets.py
"""

import http.server
import os
import shutil
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
OUTPUT_DIR = REPO_ROOT / "docs-site" / "static" / "img" / "branding"

PORT = 18923


def _copy_icon_for_serving():
    """Copy fiesta-icon.png next to the HTML so the local server can serve it."""
    src = REPO_ROOT / "fiesta-icon.png"
    dst = SCRIPTS_DIR / "fiesta-icon.png"
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
    return dst


def _start_server():
    """Start a simple HTTP server in the scripts/ directory."""
    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    icon_copy = _copy_icon_for_serving()
    original_cwd = os.getcwd()
    os.chdir(SCRIPTS_DIR)

    httpd = _start_server()
    url = f"http://127.0.0.1:{PORT}/brand-export.html"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 800, "height": 600},
                device_scale_factor=2,
            )
            page.goto(url, wait_until="networkidle")
            # Wait for Geist font to load
            page.wait_for_function(
                "document.fonts.check('900 36px Geist') && document.fonts.check('300 36px Geist')"
            )

            for variant in ("light", "dark"):
                el = page.locator(f"#{variant}-lockup")
                output_path = OUTPUT_DIR / f"logo-lockup-{variant}.png"
                el.screenshot(
                    path=str(output_path),
                    omit_background=True,
                )
                print(f"  Saved {output_path.relative_to(REPO_ROOT)}")

            browser.close()
    finally:
        httpd.shutdown()
        os.chdir(original_cwd)
        if icon_copy.exists() and icon_copy.parent == SCRIPTS_DIR:
            icon_copy.unlink()

    print("Done.")


if __name__ == "__main__":
    main()
