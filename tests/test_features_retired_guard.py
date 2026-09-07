"""Guard: the legacy ``features.*`` plugin-config branches stay retired (issue #1761).

The eleven legacy plugin-feature blocks (weather, date_time, home_assistant,
guest_wifi, star_trek_quotes, air_fog, muni, surf, baywheels, traffic, stocks)
were retired: their only live consumers were the deleted ``src/utils`` data
sources and the one-shot feature->plugin migration. Production code must not
read them through ``get_feature``/``_get_feature`` anymore.

Deliberately NOT covered by this guard:

* ``features.silence_schedule`` — a live system feature, still stored under
  ``features`` and read via ``get_feature("silence_schedule")``.
* ``FEATURE_TO_PLUGIN_MAP`` / ``_auto_migrate_features_to_plugins`` — the
  v1->v2 upgrade path still reads the raw feature dicts from old config
  files, by design.
* ``get_color_rules`` — reads a stored legacy feature block only when one is
  still present in the user's config file (manifest defaults otherwise).
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

RETIRED_FEATURE_KEYS = (
    "weather",
    "date_time",
    "home_assistant",
    "guest_wifi",
    "star_trek_quotes",
    "air_fog",
    "muni",
    "surf",
    "baywheels",
    "traffic",
    "stocks",
)

# get_feature("weather") / _get_feature('muni') / features["stocks"] ...
_KEYS = "|".join(RETIRED_FEATURE_KEYS)
_PATTERNS = [
    re.compile(rf"""_?get_feature\(\s*["']({_KEYS})["']"""),
    re.compile(rf"""features\[\s*["']({_KEYS})["']\s*\]"""),
    re.compile(rf"""features\.get\(\s*["']({_KEYS})["']"""),
]


def test_no_production_reads_of_retired_feature_keys():
    """No src/ module reads a retired features.* key through the config API."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in _PATTERNS:
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(SRC.parent)}:{lineno}: {line.strip()}")
    assert not offenders, "Retired features.* reads found in production code:\n" + "\n".join(offenders)


def test_default_config_features_holds_only_silence_schedule():
    """DEFAULT_CONFIG no longer seeds the legacy plugin-feature blocks."""
    from src.config_manager import DEFAULT_CONFIG

    assert set(DEFAULT_CONFIG["features"].keys()) == {"silence_schedule"}
