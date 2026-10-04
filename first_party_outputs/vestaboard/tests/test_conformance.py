"""The Vestaboard plugin passes FiestaBoard's output conformance suite.

One run per way to reach a board that takes the suite's 6×22 frame: the
Local API, the RW Cloud API (a 15 s floor core keeps) and the note-array
Cloud API. The plugin's real request code runs against the suite's fake
device through ``self.http``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from first_party_outputs.vestaboard import VestaboardOutput
from src.outputs.conformance import OutputConformanceSuite

PLUGIN_DIR = Path(__file__).resolve().parents[1]

CONFIGS = {
    "local": {"api_mode": "local", "host": "192.0.2.10", "local_api_key": "test_local_key_1234"},
    "rw-cloud": {"api_mode": "cloud", "cloud_key": "test_cloud_key_1234"},
    "note-array-cloud": {"device_type": "note_array", "note_array_token": "test_token_1234"},
}


def _decode(payload: Any) -> Any:
    """The frame a write carries: ``{"characters": grid}``, or the bare RW Cloud grid."""
    if isinstance(payload, dict):
        return payload.get("characters")
    return payload if isinstance(payload, list) else None


@pytest.mark.parametrize("kind", list(CONFIGS))
def test_the_plugin_is_conformant(kind):
    report = OutputConformanceSuite(
        plugin_dir=PLUGIN_DIR,
        factory=lambda board_id, config, transport: VestaboardOutput(board_id, config),
        config=CONFIGS[kind],
        decode=_decode,
    ).assert_conformant()
    assert report.plugin_id == "vestaboard"
