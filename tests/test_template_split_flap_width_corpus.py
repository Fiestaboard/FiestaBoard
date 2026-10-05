"""Split-flap width corpus: the engine's width paths, byte for byte.

Every alignment, padding, truncation, ``fill_space``, wrap and validation
width path the template engine has, run with extended markup OFF (every
split-flap board) over a corpus that includes extended-markup *spelling*
(``{red:hot}``, ``{{black/white:OPEN}}``, ``{icon:sun}``), which a split-flap
board draws as literal text. The golden in
``tests/golden/templates/split_flap_width_corpus.json`` was recorded from the
engine BEFORE rendered-width measuring for extended markup existed, so any
change to what a split-flap board receives fails here.

Re-recording: ``RECORD_WIDTH_GOLDEN=1 pytest tests/test_template_split_flap_width_corpus.py``.
Only re-record when a split-flap behaviour change is intended and reviewed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.templates.engine import TemplateEngine

GOLDEN = Path(__file__).parent / "golden" / "templates" / "split_flap_width_corpus.json"
RECORD = os.environ.get("RECORD_WIDTH_GOLDEN") == "1"

CTX = {
    "demo": {
        "short": "72",
        "long": "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG AGAIN AND AGAIN",
        "tiles": "{63}{64}{65}",
        "braces": "a{b}c {red:x}",
        "spaced": "ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN",
        "endtag": "{red}HOT{/red}",
    }
}

LINES = [
    "",
    "HELLO",
    "THIS IS A VERY LONG LINE THAT EXCEEDS THE BOARD",
    "{red:hot} {black/white:OPEN} {icon:sun}",
    "{{red:HOT}} {{black/white:OPEN}} {{icon:sun}}",
    "{{red}} ALERT {{red}} {{blue}}{{green}}",
    "{63}{64}{65}{66}{67}{68}{69}{70}{71}ABCDEFGHIJKLMNOP",
    "{red}HOT{/red} COLD{/} WARM",
    "{sun} {star} {cloud} {rain} {snow} {storm} {fog} {partly} {heart} {check} {x}",
    "A{sun}{heart}" + "B" * 20,
    "TEMP {{demo.short}} F",
    "{{demo.long}}",
    "{{demo.tiles}} {{demo.braces}} {{demo.endtag}}",
    "LEFT{{fill_space}}RIGHT",
    "A{{fill_space}}B{{fill_space}}C",
    "{{red}}{{fill_space_repeat:-}}{{red}}",
    "{{fill_space_repeat:blue}}MID{{fill_space_repeat:=}}",
    "WAY TOO LONG FOR ANY FILL{{fill_space}}SPACE AT ALL HERE",
    "{red:L}{{fill_space}}{blue:R}",
    "PRE {{demo.spaced|wrap}} POST",
    "{{red}} {{demo.long|upper|wrap}}",
    "{{demo.tiles|wrap}}",
    '{{= UPPER("formula") }} {{= COLOR("red") }}',
    "{{red:{{demo.long}}}}",
    "{left}PREFIXED",
    "{center}CENTRED",
    "{right}RIGHTED",
    "{wrap}" + "WORD " * 12,
    "{center}{wrap}{red}" + "ABCDEFGHIJ" * 4,
    "{{{{{{{{",
    "}}}} {{ }} { } {} {/}",
    "SUPERCALIFRAGILISTICEXPIALIDOCIOUSLY LONGWORD",
]

DEVICES = [
    {"device_type": "flagship"},
    {"device_type": "note"},
    {"device_type": "note_array", "notes_wide": 2, "notes_tall": 1},
]

ALIGNMENTS = ["left", "center", "right"]


@pytest.fixture(scope="module")
def engine():
    return TemplateEngine()


def _record(engine: TemplateEngine) -> dict:
    out: dict = {"render_lines": [], "helpers": [], "max_line_length": []}
    for device in DEVICES:
        for alignment in ALIGNMENTS:
            for wrap in (False, True):
                meta = [{"alignment": alignment, "wrap": wrap}] * len(LINES)
                for line in LINES:
                    # One line at a time, padded with blank rows so a wrap has room.
                    rendered = engine.render_lines([line], CTX, line_metadata=meta[:1], **device)
                    out["render_lines"].append(
                        {"device": device, "alignment": alignment, "wrap": wrap, "line": line, "out": rendered}
                    )
        # Legacy inline prefixes (no metadata) across the whole corpus at once.
        out["render_lines"].append(
            {"device": device, "legacy_prefix": True, "out": engine.render_lines(LINES, CTX, **device)}
        )
    for line in LINES:
        rendered = engine.render(line, CTX)
        out["helpers"].append(
            {
                "line": line,
                "count": engine._count_tiles(rendered),
                "trunc10": engine._truncate_to_tiles(rendered, 10),
                "align": [engine._apply_alignment(rendered, a, width=15) for a in ALIGNMENTS],
                "fill": engine._process_fill_space(rendered, width=15),
                "wrap": engine._word_wrap_tiles(rendered, 7, 11, 4),
                "word_wrap": engine._word_wrap(rendered, 7, 11, 4),
            }
        )
        out["max_line_length"].append(
            {"line": line, "cols": [engine._calculate_max_line_length(line, c) for c in (15, 22)]}
        )
    return out


def test_split_flap_width_paths_are_byte_identical_to_the_golden(engine):
    actual = _record(engine)
    if RECORD:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert actual == expected
