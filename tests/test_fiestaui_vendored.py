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
    assert provenance()["commit"] == "668e42811ef05af30426ac0d719ddbf21d8070d2"


def test_files_from_another_commit_are_pinned_files():
    # FiestaUI #338 branched before #336, so plugin-models.json keeps #336's
    # bytes; an override naming a file that is not vendored would pin nothing.
    overrides = provenance().get("files_from", {})
    assert set(overrides) <= set(PINNED)
    assert set(overrides.values()) == {"22db0b5245e89714252920824d7ad40c9c16987a"}
