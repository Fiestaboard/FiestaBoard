"""Guard: a ``ui:widget`` name must resolve to something the settings form renders.

Issue #2071: the stocks plugin declared ``"ui:widget": "stock-symbol-picker"``,
a widget the web app never implemented, so its most important field silently
degraded to a bare array input. Two drift points allow that:

1. A bundled plugin manifest declares a widget core does not know. Core only
   *warns* at load time (rejecting would uninstall plugins running ahead of
   core), so nothing failed. Here it fails CI.
2. ``KNOWN_SETTINGS_WIDGETS`` (Python) claims a widget the settings form
   (TypeScript) does not render, which hides the warning in (1) for that name.
   Every known widget must appear as a string literal in the settings-form
   source. Pre-existing gaps are listed explicitly so the set can only shrink.
"""

import json
import re
from pathlib import Path

import pytest

from src.plugins.manifest import KNOWN_SETTINGS_WIDGETS, settings_schema_ui_warnings

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
SETTINGS_FORM_DIR = REPO_ROOT / "web" / "src" / "components" / "plugin-settings"

# Widgets core accepts without a warning but the web form has no renderer for.
# Ratchet: remove an entry when its renderer lands (the test below fails if a
# listed widget gains one), never add to it.
KNOWN_BUT_UNRENDERED = frozenset({"datetime", "wsdot-route-picker"})


def _bundled_manifests() -> list[Path]:
    return sorted(PLUGINS_DIR.glob("*/manifest.json"))


@pytest.mark.parametrize("manifest_path", _bundled_manifests(), ids=lambda p: p.parent.name)
def test_bundled_plugin_declares_only_known_widgets(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    assert settings_schema_ui_warnings(manifest.get("settings_schema") or {}) == []


def _settings_form_string_literals() -> set[str]:
    literals: set[str] = set()
    for path in SETTINGS_FORM_DIR.rglob("*.ts*"):
        if "__tests__" in path.parts or ".test." in path.name or ".stories." in path.name:
            continue
        literals.update(re.findall(r"""["'`]([a-z][a-z0-9-]*)["'`]""", path.read_text()))
    return literals


def test_every_known_widget_has_a_settings_form_renderer() -> None:
    rendered = _settings_form_string_literals()
    missing = sorted(KNOWN_SETTINGS_WIDGETS - KNOWN_BUT_UNRENDERED - rendered)
    assert missing == [], (
        f"KNOWN_SETTINGS_WIDGETS lists {missing} but nothing under {SETTINGS_FORM_DIR.relative_to(REPO_ROOT)} "
        "renders it; a manifest using it would silently get the default input."
    )


def test_unrendered_allowlist_only_shrinks() -> None:
    rendered = _settings_form_string_literals()
    stale = sorted(KNOWN_BUT_UNRENDERED & rendered)
    assert stale == [], f"{stale} now have a renderer; remove them from KNOWN_BUT_UNRENDERED."
    assert KNOWN_BUT_UNRENDERED <= KNOWN_SETTINGS_WIDGETS


def test_stock_symbol_picker_is_not_a_known_widget() -> None:
    """The exact #2071 declaration must keep producing a load-time warning."""
    schema = {
        "type": "object",
        "properties": {"symbols": {"type": "array", "items": {"type": "string"}, "ui:widget": "stock-symbol-picker"}},
    }
    warnings = settings_schema_ui_warnings(schema)
    assert len(warnings) == 1 and "stock-symbol-picker" in warnings[0]
