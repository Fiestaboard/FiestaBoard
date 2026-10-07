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
    assert provenance()["commit"] == "0f73bc4045e840fb59008d6918d7ca824065fa1d"


def test_every_file_comes_from_the_one_commit():
    # Every vendored file is byte-identical at `commit`; an override would mean
    # a file pinned to some other commit.
    assert provenance().get("files_from", {}) == {}


def test_the_vendored_commit_is_the_8_1_0_release():
    # 0f73bc40 is the @fiestaboard/ui 8.1.0 release commit (tag v8.1.0), which
    # ships #342 (layoutOptions.font). The data was first vendored ahead of the
    # release from the PR branch; it now comes from the tag, so the record must
    # name the release and no longer ask to be re-vendored.
    record = provenance()
    assert 342 in record["pull_requests"]
    assert record["tag"] == "v8.1.0"
    assert record["version"] == "8.1.0"
    assert record["status"].startswith("released")
    assert "branch" not in record
