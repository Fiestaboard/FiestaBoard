"""FiestaUI parity: ``charsetIssue`` / ``charsetFallback`` / ``validateMessage``.

Plan D17 (answer 2) has core port FiestaUI's rules exactly
(``src/lib/character-sets.ts``) and prove it against the golden cases
FiestaUI exports (``tests/fixtures/fiestaui/charset-golden.json``):

- ``fallbacks``: one token parsed from ``markup`` (extended markup, case
  preserved) against a set → the issue it raises and what the set draws;
- ``messages``: ``validateMessage`` over a whole message.

The plugin-style sets the cases name (``acme_sign_v1`` …) are the
``sets`` entries, materialised here exactly as an output plugin's are.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.led.charsets import (
    BUILTIN_CHARACTER_SETS,
    charset_fallback,
    charset_issue,
    materialize_character_set,
    resolve_character_set,
    validate_message,
)
from src.markup import BoardToken, parse_line
from src.outputs.board_profile import model_character_set

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "fiestaui" / "charset-golden.json").read_text(encoding="utf-8")
)


def _plugin_sets() -> dict[str, dict]:
    made: list[dict] = []
    for case in GOLDEN["sets"]:
        made.append(materialize_character_set(case["input"], made))
    return {s["id"]: s for s in made}


PLUGIN_SETS = _plugin_sets()


def charset(set_id: str) -> dict:
    return PLUGIN_SETS.get(set_id) or BUILTIN_CHARACTER_SETS[set_id]


@pytest.mark.parametrize("case", GOLDEN["fallbacks"], ids=[c["name"] for c in GOLDEN["fallbacks"]])
def test_a_tokens_issue_and_fallback_match_fiestaui(case):
    (token,) = parse_line(case["markup"], extended_markup=True, preserve_case=True)
    assert token.to_dict() == case["token"]
    assert charset_issue(charset(case["set"]), token) == case["issue"]
    assert charset_fallback(charset(case["set"]), token).to_dict() == case["fallback"]


@pytest.mark.parametrize("case", GOLDEN["messages"], ids=[c["name"] for c in GOLDEN["messages"]])
def test_validate_message_matches_fiestaui(case):
    result = validate_message(case["message"], charset(case["set"]))
    assert result.to_dict() == {"ok": case["ok"], "issues": case["issues"]}


def test_a_set_is_also_accepted_by_its_built_in_id():
    token = BoardToken("char", value="a")
    assert charset_issue("vestaboard_v1", token) == "case"
    assert charset_fallback("vestaboard_v1", token) == BoardToken("char", value="A")
    assert validate_message("a", "vestaboard_v1").ok is False


def test_an_unknown_set_id_is_refused():
    with pytest.raises(KeyError):
        charset_fallback("no_such_set", BoardToken("char", value="A"))


def test_the_golden_covers_every_issue_reason():
    reasons = {c["issue"] for c in GOLDEN["fallbacks"]} - {None}
    assert reasons == {"char", "case", "tile", "icon", "colorSpan", "blockSpan"}


# --- a set embedded in a device model (FiestaUI #326 review fixes) --------------------------


PARTIAL = {"id": "sequence_panel_3x5", "extends": "led_3x5"}
_SET_FIELDS = ("chars", "tiles", "icons", "colorSpans", "blockSpans")


def test_a_partial_set_is_made_whole_when_resolved():
    whole = resolve_character_set(PARTIAL)
    led = BUILTIN_CHARACTER_SETS["led_3x5"]
    assert (whole["id"], whole["extends"]) == ("sequence_panel_3x5", "led_3x5")
    assert {k: whole[k] for k in _SET_FIELDS} == {k: led[k] for k in _SET_FIELDS}
    assert resolve_character_set(led) is led


def test_the_set_helpers_read_a_partial_set_as_its_whole():
    token = parse_line("{red:{icon:sun}}", extended_markup=True)[0]
    assert charset_issue(PARTIAL, token) == charset_issue("led_3x5", token)
    assert charset_fallback(PARTIAL, token) == charset_fallback("led_3x5", token)
    message = "hi {icon:sun} {66}"
    assert validate_message(message, PARTIAL).to_dict() == validate_message(message, "led_3x5").to_dict()


def test_a_models_own_set_wins_over_its_legacy_device_type():
    """FiestaUI ``characterSetForModel`` never consults ``legacy.deviceType``:
    a plugin model that sets it for old call sites keeps its own set."""
    assert model_character_set({"charset": PARTIAL, "legacy": {"deviceType": "flagship"}})["id"] == PARTIAL["id"]
    assert model_character_set({"charset": "led_5x7", "legacy": {"deviceType": "note"}})["id"] == "led_5x7"
