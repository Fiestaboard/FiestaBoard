"""Where ``src/led``'s data and golden fixtures came from.

FiestaUI is the reference implementation for LED layout and raster (plan
D15); this package is a port that must match it byte for byte. The JSON it
reads (``led-fonts.json``, ``character-sets.json``) and the golden fixtures
its tests compare against (``tests/fixtures/led/``) are copied verbatim from
one FiestaUI commit by ``scripts/led_fixtures/vendor.sh``. The hashes below
pin those bytes; ``tests/test_led_parity.py`` fails if a file drifts.

The pinned commit is on an unmerged FiestaUI branch (PR #326, Task 2 of the
LED work, at its parity-fix commit 45496c9). Re-vendor from the merged release before this ships.
"""

from __future__ import annotations

FIESTAUI_REPO = "Fiestaboard/FiestaUI"
FIESTAUI_COMMIT = "45496c90a57905840529eedf1ab9352da60e1e92"
FIESTAUI_BRANCH = "feat/led-data-layer"
FIESTAUI_NOTE = (
    "FiestaUI PR #326 (Task 2: LED fonts, character sets, device models), parity-fix commit 45496c9 "
    "on a70b719; unmerged"
)
FIESTAUI_SOURCE_DIR = "scripts/ci/tests/fixtures"

#: Repo-relative path -> sha256 of the file as vendored (identical to the
#: FiestaUI blob at FIESTAUI_COMMIT).
VENDORED_SHA256: dict[str, str] = {
    "src/led/led-fonts.json": "975e1ee0eb0eea1e0138d1eeb3217eb3f4d9b610c55cfd66d6a7f65ecb02446d",
    "src/led/character-sets.json": "3f5705bb7746f817e91fc685e65616bb4470aa1496068bf72db994c3de5b6e91",
    "tests/fixtures/led/led-golden.json": "df3abbd9a0ea2e3492fd6e04c874e97cb6c0dd57cf85e745779764794df4d254",
    "tests/fixtures/led/charset-golden.json": "9e00ca0d500e6df8b02b3486c49ae4659734e9c8347ef057f23ed0ab7d6d72e3",
    "tests/fixtures/led/device-models.json": "31813828d483c6a15fd14de73ca9b9ab648b62f7edaeed1e9ac4b504e20f363c",
}
