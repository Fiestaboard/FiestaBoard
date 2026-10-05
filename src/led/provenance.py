"""Where ``src/led``'s data and golden fixtures came from.

FiestaUI is the reference implementation for LED layout and raster (plan
D15); this package is a port that must match it byte for byte. The JSON it
reads (``led-fonts.json``, ``character-sets.json``) and the golden fixtures
its tests compare against (``tests/fixtures/led/``) are copied verbatim from
one FiestaUI commit by ``scripts/led_fixtures/vendor.sh``. The hashes below
pin those bytes; ``tests/test_led_parity.py`` fails if a file drifts.

The pinned commit is on an unmerged FiestaUI branch: Task 4 (LED transitions,
PR #328, 892fd60: stable glyph keys) on Task 3 (PR #327) on Task 2 (PR #326,
bb43600: no global glyph registry). Re-vendor from the merged release before
this ships.
"""

from __future__ import annotations

FIESTAUI_REPO = "Fiestaboard/FiestaUI"
FIESTAUI_COMMIT = "892fd603c569454e87dfebb8b9ac2ade81e6563d"
FIESTAUI_BRANCH = "feat/led-transitions"
FIESTAUI_NOTE = (
    "FiestaUI PR #328 (Task 4: LED transitions, 892fd60) on PR #327 (Task 3) on PR #326 (Task 2, bb43600); unmerged"
)
FIESTAUI_SOURCE_DIR = "scripts/ci/tests/fixtures"

#: Repo-relative path -> sha256 of the file as vendored (identical to the
#: FiestaUI blob at FIESTAUI_COMMIT).
VENDORED_SHA256: dict[str, str] = {
    "src/led/led-fonts.json": "975e1ee0eb0eea1e0138d1eeb3217eb3f4d9b610c55cfd66d6a7f65ecb02446d",
    "src/led/character-sets.json": "3f5705bb7746f817e91fc685e65616bb4470aa1496068bf72db994c3de5b6e91",
    "tests/fixtures/led/led-golden.json": "5c8d1f3fe2b3e223826f3b505b1fb7e996c45e0f6f7208ef13eb5ceffd4a4b1f",
    "tests/fixtures/led/charset-golden.json": "9e00ca0d500e6df8b02b3486c49ae4659734e9c8347ef057f23ed0ab7d6d72e3",
    "tests/fixtures/led/device-models.json": "31813828d483c6a15fd14de73ca9b9ab648b62f7edaeed1e9ac4b504e20f363c",
}
