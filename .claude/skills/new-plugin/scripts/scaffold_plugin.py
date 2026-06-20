#!/usr/bin/env python3
"""Scaffold a complete FiestaBoard plugin (standalone published repo or bundled in-repo).

This script emits the *deterministic boilerplate* of a plugin: the file tree, the
naming transforms, the CI + release workflows, the test harness, the docs skeleton,
and a placeholder board image. The skeleton is GREEN BY DEFAULT — its tests pass the
moment it is generated — so the agent that runs it can immediately verify the harness
works, then replace the example logic with the real data source while keeping tests green.

Why a script and not hand-authored files: the naming invariants (slug -> id -> class
name -> import path -> repo name) and the symlink-based CI contract are mechanical and
easy to get subtly wrong by hand. Generating them removes that whole class of error so
the agent can spend its attention on the part that actually needs judgment: the data
fetching, the manifest variables, and the docs.

Usage:
    python scaffold_plugin.py \
        --slug currency \
        --name "Currency Exchange" \
        --description "Display live currency exchange rates on your board." \
        --author "FiestaBoard Team" \
        --category data \
        --icon banknote \
        --type http \
        --output-dir /path/to/workspace

    # Bundled in-repo plugin instead of a standalone repo:
    python scaffold_plugin.py --slug my-thing --name "My Thing" --bundled \
        --output-dir /path/to/FiestaBoard

Types:
    simple   no network; fetch_data computes example data locally (like date_time)
    http     fetches from an HTTP API with requests; tests mock requests.get (like dad_jokes)

Other plugin shapes (art, trigger, webhook) start from one of these two and are
hand-extended — see references/plugin-types.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import zlib
from datetime import datetime
from pathlib import Path

VALID_CATEGORIES = {"art", "data", "transit", "weather", "entertainment", "utility", "home"}


# --------------------------------------------------------------------------- #
# Naming transforms — the invariants every plugin must satisfy.
# --------------------------------------------------------------------------- #
def derive_names(slug: str) -> dict:
    """Derive every name form from the kebab-case slug.

    slug         currency-exchange     (kebab, what the user picks)
    id           currency_exchange     (snake; manifest id == dir == import name)
    repo         fiestaboard-plugin--currency-exchange
    class_name   CurrencyExchangePlugin
    """
    slug = slug.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slug):
        raise SystemExit(
            f"Invalid slug {slug!r}. Use lowercase kebab-case, e.g. 'tide-times' or 'currency'."
        )
    plugin_id = slug.replace("-", "_")
    class_name = "".join(part.capitalize() for part in plugin_id.split("_")) + "Plugin"
    return {
        "slug": slug,
        "id": plugin_id,
        "repo": f"fiestaboard-plugin--{slug}",
        "class_name": class_name,
    }


def render(template: str, tokens: dict) -> str:
    out = template
    for key, value in tokens.items():
        out = out.replace(f"__{key}__", str(value))
    return out


# --------------------------------------------------------------------------- #
# Placeholder board image — a 22x6 tile grid (Vestaboard flagship geometry).
# Pure stdlib PNG writer so we need no Pillow. MUST be replaced with a real
# board render before opening the registry PR.
# --------------------------------------------------------------------------- #
def write_placeholder_png(path: Path) -> None:
    cols, rows, scale = 22, 6, 18
    width, height = cols * scale, rows * scale
    # Simple FiestaBoard-ish palette cycled across tiles.
    palette = [
        (24, 24, 28), (200, 60, 60), (220, 130, 40), (220, 200, 60),
        (60, 160, 90), (60, 120, 200), (120, 80, 180), (235, 235, 235),
    ]
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 for each scanline
        ty = y // scale
        for x in range(width):
            tx = x // scale
            # 1px gap between tiles -> board look
            if x % scale == 0 or y % scale == 0:
                raw.extend((12, 12, 14))
            else:
                raw.extend(palette[(tx + ty) % len(palette)])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(bytes(raw), 9)
    path.write_bytes(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


# --------------------------------------------------------------------------- #
# File templates. Tokens are __UPPER__ to avoid clashing with JSON/Python braces.
# --------------------------------------------------------------------------- #

INIT_HTTP = '''"""__NAME__ plugin for FiestaBoard.

__DESCRIPTION__
"""

from typing import Any, Dict, List, Optional
import logging

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# TODO: point these at your real data source.
API_URL = "https://example.com/api"
USER_AGENT = "FiestaBoard __NAME__ Plugin (https://github.com/Fiestaboard/__REPO__)"


class __CLASS_NAME__(PluginBase):
    """__NAME__ plugin.

    Fetches data from an HTTP API and exposes it as template variables.
    The scaffolded body returns two example variables (`value`, `status`) so the
    test suite is green out of the box. Replace the request + parsing below with
    your real source, and keep the manifest `variables`, the data dict keys, and
    the tests in sync.
    """

    @property
    def plugin_id(self) -> str:
        return "__ID__"

    def fetch_data(self) -> PluginResult:
        try:
            response = requests.get(
                API_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()

            # TODO: map the API payload onto your declared manifest variables.
            return PluginResult(
                available=True,
                data={
                    "value": str(payload.get("value", "123")),
                    "status": str(payload.get("status", "OK")),
                },
            )
        except Exception as e:  # fetch_data must never raise -- surface as unavailable
            logger.exception("Error fetching __ID__ data")
            return PluginResult(available=False, error=str(e))

    def get_formatted_display(self) -> Optional[List[str]]:
        """Optional 6-line fallback rendering when a user has no custom template."""
        result = self.get_data()
        if not result.available or not result.data:
            return None
        lines = [
            "__NAME_UPPER__",
            "",
            f"Value: {result.data.get('value', '')}",
            f"Status: {result.data.get('status', '')}",
            "",
            "",
        ]
        while len(lines) < 6:
            lines.append("")
        return [line[:22] for line in lines[:6]]


# Export hook: the loader looks for a module-level `Plugin`.
Plugin = __CLASS_NAME__
'''

INIT_SIMPLE = '''"""__NAME__ plugin for FiestaBoard.

__DESCRIPTION__
"""

from typing import Any, Dict, List, Optional
import logging

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class __CLASS_NAME__(PluginBase):
    """__NAME__ plugin.

    Computes its data locally (no network). The scaffolded body returns two example
    variables (`value`, `status`) so the test suite is green out of the box. Replace
    the computation below with your real logic, and keep the manifest `variables`,
    the data dict keys, and the tests in sync.
    """

    @property
    def plugin_id(self) -> str:
        return "__ID__"

    def fetch_data(self) -> PluginResult:
        try:
            # TODO: compute your real values here.
            return PluginResult(
                available=True,
                data={
                    "value": "123",
                    "status": "OK",
                },
            )
        except Exception as e:  # fetch_data must never raise -- surface as unavailable
            logger.exception("Error computing __ID__ data")
            return PluginResult(available=False, error=str(e))

    def get_formatted_display(self) -> Optional[List[str]]:
        """Optional 6-line fallback rendering when a user has no custom template."""
        result = self.get_data()
        if not result.available or not result.data:
            return None
        lines = [
            "__NAME_UPPER__",
            "",
            f"Value: {result.data.get('value', '')}",
            f"Status: {result.data.get('status', '')}",
            "",
            "",
        ]
        while len(lines) < 6:
            lines.append("")
        return [line[:22] for line in lines[:6]]


# Export hook: the loader looks for a module-level `Plugin`.
Plugin = __CLASS_NAME__
'''

MANIFEST = {
    "id": "__ID__",
    "name": "__NAME__",
    "version": "1.0.0",
    "description": "__DESCRIPTION__",
    "author": "__AUTHOR__",
    "repository": "https://github.com/Fiestaboard/__REPO__",
    "documentation": "README.md",
    "icon": "__ICON__",
    "category": "__CATEGORY__",
    "fiestaboard_version": ">=4.2.0",
    "min_refresh_seconds": 60,
    "settings_schema": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "title": "Enable __NAME__", "default": False},
            "refresh_seconds": {
                "type": "integer",
                "title": "Refresh Interval (seconds)",
                "description": "How often to fetch new data.",
                "default": 300,
                "minimum": 60,
                "maximum": 3600,
            },
        },
    },
    "variables": {
        "groups": {"main": {"label": "__NAME__"}},
        "simple": {
            "value": {
                "description": "The primary data value",
                "type": "string",
                "max_length": 22,
                "group": "main",
                "example": "123",
            },
            "status": {
                "description": "Current status text",
                "type": "string",
                "max_length": 22,
                "group": "main",
                "example": "OK",
            },
        },
    },
    "screenshots": [
        {
            "src": "docs/board-display.png",
            "alt": "__NAME__ displayed on a Vestaboard",
            "caption": "Example board output using the default template",
            "primary": True,
        }
    ],
    "demo": {
        "flagship": {
            "name": "__NAME__ Demo",
            "template": ["", "{{__ID__.status}}", "Value: {{__ID__.value}}", "", "", ""],
            "line_metadata": [{"alignment": "center", "wrap": False} for _ in range(6)],
        }
    },
}

CONFTEST = '''"""Plugin test fixtures and configuration for __ID__."""

import pytest

from src.plugins.testing import create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response
'''

TEST_HTTP = '''"""Tests for the __ID__ plugin."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from plugins.__ID__ import __CLASS_NAME__
from src.plugins.base import PluginResult

MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"


@pytest.fixture
def manifest_data():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


@pytest.fixture
def plugin(manifest_data):
    return __CLASS_NAME__(manifest_data)


class Test__CLASS_NAME__:
    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "__ID__"

    @patch("plugins.__ID__.requests.get")
    def test_fetch_data_success(self, mock_get, plugin):
        mock_response = Mock()
        mock_response.json.return_value = {"value": "123", "status": "OK"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None

    @patch("plugins.__ID__.requests.get")
    def test_fetch_data_returns_all_declared_variables(self, mock_get, plugin, manifest_data):
        mock_response = Mock()
        mock_response.json.return_value = {"value": "123", "status": "OK"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = plugin.fetch_data()

        declared = manifest_data["variables"]["simple"]
        for var in declared:
            assert var in result.data, f"Variable '{var}' declared in manifest but not in data"

    @patch("plugins.__ID__.requests.get")
    def test_fetch_data_api_error(self, mock_get, plugin):
        mock_get.side_effect = Exception("Network error")
        result = plugin.fetch_data()
        assert result.available is False
        assert result.error is not None
        assert "Network error" in result.error

    @patch("plugins.__ID__.requests.get")
    def test_get_formatted_display(self, mock_get, plugin):
        mock_response = Mock()
        mock_response.json.return_value = {"value": "123", "status": "OK"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert all(isinstance(line, str) and len(line) <= 22 for line in lines)


class TestManifestMetadata:
    def test_manifest_uses_dict_simple_format(self, manifest_data):
        assert isinstance(manifest_data["variables"]["simple"], dict)

    def test_all_variables_have_descriptions(self, manifest_data):
        for var_name, meta in manifest_data["variables"]["simple"].items():
            assert meta.get("description"), f"Variable '{var_name}' missing description"

    def test_groups_are_defined(self, manifest_data):
        groups = manifest_data["variables"].get("groups", {})
        assert len(groups) > 0
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"

    def test_all_variables_reference_valid_groups(self, manifest_data):
        groups = set(manifest_data["variables"].get("groups", {}).keys())
        for var_name, meta in manifest_data["variables"]["simple"].items():
            group = meta.get("group", "")
            if group:
                assert group in groups, f"Variable '{var_name}' references undefined group '{group}'"
'''

TEST_SIMPLE = '''"""Tests for the __ID__ plugin."""

import json
from pathlib import Path

import pytest

from plugins.__ID__ import __CLASS_NAME__
from src.plugins.base import PluginResult

MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"


@pytest.fixture
def manifest_data():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


@pytest.fixture
def plugin(manifest_data):
    return __CLASS_NAME__(manifest_data)


class Test__CLASS_NAME__:
    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "__ID__"

    def test_fetch_data_success(self, plugin):
        result = plugin.fetch_data()
        assert result.available is True
        assert result.error is None
        assert result.data is not None

    def test_fetch_data_returns_all_declared_variables(self, plugin, manifest_data):
        result = plugin.fetch_data()
        declared = manifest_data["variables"]["simple"]
        for var in declared:
            assert var in result.data, f"Variable '{var}' declared in manifest but not in data"

    def test_get_formatted_display(self, plugin):
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert all(isinstance(line, str) and len(line) <= 22 for line in lines)


class TestManifestMetadata:
    def test_manifest_uses_dict_simple_format(self, manifest_data):
        assert isinstance(manifest_data["variables"]["simple"], dict)

    def test_all_variables_have_descriptions(self, manifest_data):
        for var_name, meta in manifest_data["variables"]["simple"].items():
            assert meta.get("description"), f"Variable '{var_name}' missing description"

    def test_groups_are_defined(self, manifest_data):
        groups = manifest_data["variables"].get("groups", {})
        assert len(groups) > 0
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"

    def test_all_variables_reference_valid_groups(self, manifest_data):
        groups = set(manifest_data["variables"].get("groups", {}).keys())
        for var_name, meta in manifest_data["variables"]["simple"].items():
            group = meta.get("group", "")
            if group:
                assert group in groups, f"Variable '{var_name}' references undefined group '{group}'"
'''

# test_demo_pages.py is verbatim across every published repo — it reads id + variables
# from the manifest at runtime and needs no per-plugin edits. Copied exactly.
TEST_DEMO_PAGES = '''"""Validates that demo page templates in manifest.json only use defined variables."""
import json
import re
from pathlib import Path

import pytest

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "manifest.json"
_SYSTEM_PREFIXES = {"date_time"}


def _load_manifest():
    return json.loads(_MANIFEST_PATH.read_text())


def _valid_refs(plugin_id: str, manifest: dict) -> set:
    variables = manifest.get("variables", {})
    simple = variables.get("simple", {})
    arrays = variables.get("arrays", {})

    valid = set()
    for var in simple:
        valid.add(f"{plugin_id}.{var}")
        valid.add(var)
    for arr_name, arr_spec in arrays.items():
        fields = arr_spec.get("item_fields", [])
        sub_arrays = arr_spec.get("sub_arrays", {})
        for i in range(10):
            for field in fields:
                valid.add(f"{plugin_id}.{arr_name}.{i}.{field}")
                valid.add(f"{arr_name}.{i}.{field}")
            for sub_name, sub_spec in sub_arrays.items():
                for j in range(20):
                    for field in sub_spec.get("item_fields", []):
                        valid.add(f"{plugin_id}.{arr_name}.{i}.{sub_name}.{j}.{field}")
                        valid.add(f"{arr_name}.{i}.{sub_name}.{j}.{field}")
    return valid


def _demo_cases() -> list:
    manifest = _load_manifest()
    demo = manifest.get("demo", {})
    return [
        (device_type, entry.get("template", []))
        for device_type, entry in demo.items()
    ]


@pytest.mark.parametrize("device_type,template", _demo_cases())
def test_demo_variables_are_defined(device_type: str, template: list) -> None:
    """All {{variable}} references in each demo template must be declared in manifest variables."""
    manifest = _load_manifest()
    plugin_id = manifest.get("id", "")
    valid = _valid_refs(plugin_id, manifest)

    invalid = []
    for line in template:
        for m in re.finditer(r'\\{\\{([^}]+)\\}\\}', line):
            ref = m.group(1).strip()
            prefix = ref.split(".")[0]
            if prefix in _SYSTEM_PREFIXES:
                continue
            if ref not in valid:
                invalid.append(ref)

    assert not invalid, (
        f"Demo '{device_type}' references undefined variables: {invalid}"
    )
'''

CI_YML = '''name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/checkout@v4
        with:
          repository: Fiestaboard/FiestaBoard
          path: fiestaboard-core

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r fiestaboard-core/requirements.txt
          pip install pytest pytest-cov
          # Add any extra runtime deps your plugin imports here, e.g.:
          # pip install icalendar recurring-ical-events

      - name: Validate manifest
        run: |
          python -c "
          import json
          with open('manifest.json') as f:
              m = json.load(f)
          for field in ['id', 'name', 'version']:
              assert field in m, f'Missing required field: {field}'
          print('manifest.json is valid')
          "

      - name: Set up plugin directory structure
        run: |
          PLUGIN_ID=$(python -c "import json; print(json.load(open('manifest.json'))['id'])")
          mkdir -p plugins
          touch plugins/__init__.py
          ln -s .. "plugins/$PLUGIN_ID"
          ln -s . "$PLUGIN_ID"

      - name: Run tests
        env:
          PYTHONPATH: "${{ github.workspace }}:fiestaboard-core"
          BOARD_READ_WRITE_KEY: test_key
        run: |
          cat > .coveragerc << 'RCEOF'
          [run]
          omit = fiestaboard-core/*
          RCEOF
          pytest tests/ -v \\
            --cov=. \\
            --cov-report=term-missing \\
            --cov-fail-under=70 \\
            --ignore=fiestaboard-core
'''

RELEASE_YML = '''name: Release

# Tags + publishes a GitHub Release whenever the version in manifest.json changes
# on main. Bump the "version" field in manifest.json, merge to main, and this
# creates v<version> automatically. Idempotent: re-runs are a no-op once the tag exists.

on:
  push:
    branches: [main]
    paths:
      - manifest.json
  workflow_dispatch:

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Read manifest version
        id: ver
        run: |
          VERSION=$(python -c "import json; print(json.load(open('manifest.json'))['version'])")
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"

      - name: Tag and release if the version is new
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          VERSION="${{ steps.ver.outputs.version }}"
          TAG="v$VERSION"
          if git rev-parse "$TAG" >/dev/null 2>&1; then
            echo "Tag $TAG already exists - nothing to release."
            exit 0
          fi
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "$TAG"
          git push origin "$TAG"
          gh release create "$TAG" --title "$TAG" \\
            --notes "Release $TAG (manifest version $VERSION)."
'''

README = '''# __NAME__ Plugin

__DESCRIPTION__

![__NAME__ Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)**

## Overview

__NAME__ displays data on your FiestaBoard. <!-- TODO: 2-3 sentences on what it shows and where the data comes from. -->

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{__ID__.value}}` | The primary data value | `123` |
| `{{__ID__.status}}` | Current status text | `OK` |

## Example Templates

```jinja
{center}__NAME_UPPER__
Value: {{__ID__.value}}
{{__ID__.status}}
```

## Configuration

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `enabled` | boolean | No | false | Enable/disable the plugin |
| `refresh_seconds` | integer | No | 300 | How often to fetch new data (seconds) |

## Features

- <!-- TODO: capability one -->
- <!-- TODO: capability two -->

## Author

__AUTHOR__
'''

SETUP = '''# __NAME__ Setup Guide

__DESCRIPTION__

## Overview

**What it does:**
- <!-- TODO: feature one -->
- <!-- TODO: feature two -->

**Prerequisites:**
- <!-- TODO: API key / account / nothing -->

## Quick Setup

### 1. Enable the Plugin

In the FiestaBoard web UI:
1. Go to **Integrations**
2. Find **__NAME__** and toggle it **On**

### 2. Configure __NAME__

1. Click the **Configure** button
2. Adjust settings as needed
3. Click **Save Changes**

### 3. Create a Board Template

1. Go to **Pages** in the web UI
2. Click **Create Page** or edit an existing page
3. Add plugin variables using the variable picker or type them directly

```jinja
{center}__NAME_UPPER__
Value: {{__ID__.value}}
{{__ID__.status}}
```

### 4. View on Your Board

Once configured, the plugin output displays on your board when the page is active.

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{__ID__.value}}` | The primary data value | `123` |
| `{{__ID__.status}}` | Current status text | `OK` |

## Configuration Reference

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `enabled` | boolean | No | false | Enable/disable the plugin |
| `refresh_seconds` | integer | No | 300 | How often to fetch new data (seconds) |

## Troubleshooting

**Issue: Plugin shows "Not Available"**
- <!-- TODO: most common cause -->
- Check the Docker logs for error messages: `docker compose logs -f`
'''

GITIGNORE = '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.env
.env.local
*.egg-info/
dist/
build/
.coverage
.coverage.*
htmlcov/
.pytest_cache/
.mypy_cache/

# Local CI symlink scaffold (recreated by ci.yml and by run_tests.sh)
/plugins/
/__SLUG__/

# Editor
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
'''

LICENSE = '''MIT License

Copyright (c) __YEAR__ Fiestaboard contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

# Local convenience: replicate the CI symlink contract so `pytest` runs green on
# the host exactly the way it does in GitHub Actions. Requires the core repo on
# PYTHONPATH (pass its path as $1, defaults to a sibling FiestaBoard checkout).
RUN_TESTS_SH = '''#!/usr/bin/env bash
# Run this plugin's tests the same way CI does.
# Usage: ./run_tests.sh [path-to-FiestaBoard-core]   (default: ../FiestaBoard)
set -euo pipefail

CORE="${1:-../FiestaBoard}"
if [ ! -d "$CORE/src/plugins" ]; then
  echo "FiestaBoard core not found at: $CORE" >&2
  echo "Pass the path to your FiestaBoard checkout: ./run_tests.sh /path/to/FiestaBoard" >&2
  exit 1
fi
CORE_ABS="$(cd "$CORE" && pwd)"
PLUGIN_ID=$(python3 -c "import json; print(json.load(open('manifest.json'))['id'])")

# Recreate the import scaffold CI builds (ignored by git).
mkdir -p plugins
touch plugins/__init__.py
[ -e "plugins/$PLUGIN_ID" ] || ln -s .. "plugins/$PLUGIN_ID"
[ -e "$PLUGIN_ID" ] || ln -s . "$PLUGIN_ID"

PYTHONPATH="$(pwd):$CORE_ABS" pytest tests/ -v \\
  --cov=. --cov-report=term-missing --cov-fail-under=70 --ignore="$CORE_ABS"
'''


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if executable:
        path.chmod(0o755)


def build_standalone(root: Path, tokens: dict, ptype: str) -> list:
    init_tmpl = INIT_HTTP if ptype == "http" else INIT_SIMPLE
    test_tmpl = TEST_HTTP if ptype == "http" else TEST_SIMPLE

    manifest = json.loads(render(json.dumps(MANIFEST), tokens))

    created = []

    def emit(rel: str, content: str, **kw):
        write(root / rel, content, **kw)
        created.append(rel)

    emit("__init__.py", render(init_tmpl, tokens))
    emit("manifest.json", json.dumps(manifest, indent=2) + "\n")
    emit("README.md", render(README, tokens))
    emit("docs/SETUP.md", render(SETUP, tokens))
    emit(".gitignore", render(GITIGNORE, tokens))
    emit("LICENSE", render(LICENSE, tokens))
    emit(".github/workflows/ci.yml", CI_YML)
    emit(".github/workflows/release.yml", RELEASE_YML)
    emit("run_tests.sh", RUN_TESTS_SH, executable=True)
    emit("tests/__init__.py", f'"""Tests for the {tokens["ID"]} plugin."""\n')
    emit("tests/conftest.py", render(CONFTEST, tokens))
    emit("tests/test_plugin.py", render(test_tmpl, tokens))
    emit("tests/test_demo_pages.py", TEST_DEMO_PAGES)

    write_placeholder_png(root / "docs" / "board-display.png")
    created.append("docs/board-display.png  (PLACEHOLDER — replace with a real board render)")
    return created


def build_bundled(root: Path, tokens: dict, ptype: str) -> list:
    """Bundled in-repo plugin: lives in <main-repo>/plugins/<id>/, no CI/release/LICENSE.

    Runs under the main repo's own pytest + coverage config, so no symlink scaffold
    and no standalone CI is needed.
    """
    init_tmpl = INIT_HTTP if ptype == "http" else INIT_SIMPLE
    test_tmpl = TEST_SIMPLE if ptype != "http" else TEST_HTTP
    # Bundled tests import via plugins.<id> just like standalone, which resolves
    # natively inside the main repo (real plugins/<id>/ directory on disk).
    manifest = json.loads(render(json.dumps(MANIFEST), tokens))
    created = []

    def emit(rel: str, content: str, **kw):
        write(root / rel, content, **kw)
        created.append(rel)

    emit("__init__.py", render(init_tmpl, tokens))
    emit("manifest.json", json.dumps(manifest, indent=2) + "\n")
    emit("README.md", render(README, tokens))
    emit("docs/SETUP.md", render(SETUP, tokens))
    emit("tests/__init__.py", f'"""Tests for the {tokens["ID"]} plugin."""\n')
    emit("tests/conftest.py", render(CONFTEST, tokens))
    emit("tests/test_plugin.py", render(test_tmpl, tokens))
    write_placeholder_png(root / "docs" / "board-display.png")
    created.append("docs/board-display.png  (PLACEHOLDER — replace with a real board render)")
    return created


def main() -> int:
    p = argparse.ArgumentParser(description="Scaffold a FiestaBoard plugin.")
    p.add_argument("--slug", required=True, help="kebab-case slug, e.g. 'tide-times'")
    p.add_argument("--name", required=True, help='Display name, e.g. "Tide Times"')
    p.add_argument("--description", required=True, help="One-sentence description.")
    p.add_argument("--author", default="FiestaBoard Team")
    p.add_argument("--category", default="utility", choices=sorted(VALID_CATEGORIES))
    p.add_argument("--icon", default="puzzle", help="Lucide icon name.")
    p.add_argument("--type", default="http", choices=["http", "simple"], dest="ptype")
    p.add_argument(
        "--output-dir",
        required=True,
        help="Where to create the plugin. Standalone: the parent dir (repo created as "
        "<output-dir>/fiestaboard-plugin--<slug>). Bundled: the main repo (created as "
        "<output-dir>/plugins/<id>).",
    )
    p.add_argument("--bundled", action="store_true", help="Generate an in-repo plugin instead of a standalone repo.")
    p.add_argument("--force", action="store_true", help="Overwrite an existing target directory.")
    args = p.parse_args()

    names = derive_names(args.slug)
    try:
        year = datetime.now().year
    except Exception:
        year = 2026

    tokens = {
        "ID": names["id"],
        "SLUG": names["slug"],
        "REPO": names["repo"],
        "CLASS_NAME": names["class_name"],
        "NAME": args.name,
        "NAME_UPPER": args.name.upper(),
        "DESCRIPTION": args.description,
        "AUTHOR": args.author,
        "CATEGORY": args.category,
        "ICON": args.icon,
        "YEAR": year,
    }

    out = Path(args.output_dir).expanduser().resolve()
    if args.bundled:
        root = out / "plugins" / names["id"]
    else:
        root = out / names["repo"]

    if root.exists() and any(root.iterdir()) and not args.force:
        print(f"ERROR: {root} already exists and is non-empty. Use --force to overwrite.", file=sys.stderr)
        return 1

    created = build_bundled(root, tokens, args.ptype) if args.bundled else build_standalone(root, tokens, args.ptype)

    print(f"Scaffolded {'bundled' if args.bundled else 'standalone'} plugin at: {root}\n")
    print("Names:")
    print(f"  slug   {names['slug']}")
    print(f"  id     {names['id']}   (manifest id == import name == dir)")
    print(f"  class  {names['class_name']}")
    if not args.bundled:
        print(f"  repo   {names['repo']}")
    print("\nFiles:")
    for rel in created:
        print(f"  {rel}")
    helper = Path(__file__).resolve().parent / "run_tests_in_container.sh"
    print("\nNext:")
    if args.bundled:
        print("  - Run tests in the dev container:")
        print(f"      docker compose -f docker-compose.dev.yml exec fiestaboard \\")
        print(f"        python scripts/run_plugin_tests.py --plugin={names['id']}")
    else:
        print("  - Verify the green skeleton passes BEFORE changing anything")
        print("    (runs in the dev container, exactly like CI):")
        print(f"      {helper} \\")
        print(f"        {root}")
        print("    (the repo's own ./run_tests.sh is a host-venv fallback for end users.)")
    print("  - Then implement fetch_data, refine manifest variables, and write the docs,")
    print("    keeping manifest variables, returned data keys, and the demo template in sync.")
    print("  - Replace docs/board-display.png with a real board render before registering.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
