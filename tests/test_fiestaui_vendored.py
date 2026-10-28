"""FiestaUI's vendored data is exactly the bytes ``src/fiestaui/provenance.json`` pins.

One record covers every copied file: the runtime data in ``src/fiestaui/``
(schemas, built-in character sets, device models, LED fonts) and the golden
fixtures in ``tests/fixtures/fiestaui/`` that the output-manifest, LED
raster and LED transition tests compare against. Re-vendor with
``scripts/fiestaui_fixtures/vendor.sh`` and update the record in one PR.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.fiestaui import DATA_DIR, provenance

ROOT = Path(__file__).resolve().parent.parent
GOLDENS = ROOT / "tests" / "fixtures" / "fiestaui"
PINNED = provenance()["files"]


@pytest.mark.parametrize("path", sorted(PINNED))
def test_each_vendored_file_is_the_one_provenance_pins(path):
    digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    assert digest == PINNED[path], f"{path} changed since it was vendored from FiestaUI {provenance()['commit']}"


def test_every_vendored_file_is_pinned():
    # A file copied in without a hash would go unchecked.
    on_disk = {
        str(p.relative_to(ROOT))
        for p in [*DATA_DIR.glob("*.json"), *GOLDENS.glob("*.json")]
        if p.name != "provenance.json"
    }
    assert set(PINNED) == on_disk


def test_provenance_records_one_fiestaui_commit():
    assert provenance()["source"] == "Fiestaboard/FiestaUI"
    assert provenance()["commit"] == "2df29c78167e56b790b637769e195f83a580954b"


def test_every_file_comes_from_the_one_commit():
    # Every vendored file is byte-identical at `commit`; an override would mean
    # a file pinned to some other commit.
    assert provenance().get("files_from", {}) == {}


def test_the_vendored_commit_is_the_8_4_0_release():
    # 2df29c78 is the @fiestaboard/ui 8.4.0 release commit (tag v8.4.0), which
    # ships #343 (LED bitmap layers and their goldens) on top of #341 (the
    # Pixoo 64 streams at 5 fps, 8.3.0) and #342 (layoutOptions.font, 8.1.0).
    record = provenance()
    assert {341, 342, 343} <= set(record["pull_requests"])
    assert record["tag"] == "v8.4.0"
    assert record["version"] == "8.4.0"
    assert record["status"].startswith("released")
    assert "branch" not in record
