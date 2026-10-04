"""Shared helpers: a plugin instance whose ``self.http`` talks to a scripted device."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

from first_party_outputs.vestaboard import VestaboardOutput
from src.plugins import CancelToken
from src.plugins.manifest import load_manifest

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def response(status: int = 200, body: Any = None, headers: dict[str, str] | None = None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps({} if body is None else body).encode()
    resp.headers.update(headers or {})
    resp.headers["Content-Type"] = "application/json"
    return resp


class Device:
    """Records every request the plugin makes and answers from a script.

    ``answer`` is ``(request) -> Response | BaseException | None``; ``None``
    (the default) answers 200 ``{}``.
    """

    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.answer: Callable[[Any], Any] = lambda request: None

    def __call__(self, request: Any) -> requests.Response:
        self.requests.append(request)
        outcome = self.answer(request)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome if outcome is not None else response()

    @property
    def urls(self) -> list[str]:
        return [r.url for r in self.requests]


@pytest.fixture
def manifest():
    parsed, errors = load_manifest(PLUGIN_DIR / "manifest.json")
    assert not errors, errors
    return parsed


@pytest.fixture
def make(manifest):
    """``make(config) -> (plugin, device)``: a bound instance on a fake device."""

    def build(config: dict, board_id: str | None = "b1") -> tuple[VestaboardOutput, Device]:
        plugin = VestaboardOutput(board_id, config)
        plugin.bind_manifest(manifest.output)
        device = Device()
        plugin.http.use_transport(device)
        return plugin, device

    return build


def grid(fill: int = 0, rows: int = 6, cols: int = 22) -> list[list[int]]:
    return [[fill] * cols for _ in range(rows)]


def token() -> CancelToken:
    return CancelToken()


LOCAL = {"api_mode": "local", "host": "192.0.2.10", "local_api_key": "test_local_key"}
CLOUD = {"api_mode": "cloud", "cloud_key": "test_cloud_key"}
NOTE_ARRAY_CLOUD = {"device_type": "note_array", "note_array_token": "test_token", "notes_wide": 2, "notes_tall": 1}


def tile(row: int, col: int, host: str, **extra: Any) -> dict:
    return {"row": row, "col": col, "host": host, "local_api_key": f"test_key_{row}_{col}", **extra}


TILES = {
    "api_mode": "local",
    "device_type": "note_array",
    "notes_wide": 2,
    "notes_tall": 1,
    "tiles": [tile(0, 0, "192.0.2.21"), tile(0, 1, "192.0.2.22", port=7001)],
}
