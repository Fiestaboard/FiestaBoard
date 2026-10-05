"""LED transitions: FiestaUI's golden sequences, the flip's rules and the transition menu.

``tests/fixtures/led/led-golden.json`` ``transitions`` holds FiestaUI's
``ledTransitionFrames(planLedTransition(from, to, resolvedSpec), fps)`` for
each case: every frame a device receives, as RGB888. A port must give the
same frames, byte for byte, frame for frame. The flip's scramble is seeded,
so the goldens pin FiestaBoard's own scramble (hash32 + mulberry32).

The other cases are ports of FiestaUI's ``led-transitions.test.ts`` and
``led-transition-registry.test.ts`` (c2c3b72).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from src.led import (
    BUILTIN_CHARACTER_SETS,
    LedLayoutOptions,
    LedMatrixSpec,
    frame_to_ascii,
    layout_message,
    materialize_character_set,
    rasterize,
)
from src.led.transition_registry import (
    LED_TRANSITIONS,
    default_transition_id_for_model,
    resolve_led_transition,
    transition_spec_for_device,
    transitions_for_model,
)
from src.led.transitions import (
    LED_TRANSITION_KINDS,
    LedTransitionSpec,
    plan_transition,
    scramble_pool,
    transition_frames,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "led"
GOLDEN = json.loads((FIXTURES / "led-golden.json").read_text(encoding="utf-8"))
MODELS = json.loads((FIXTURES / "device-models.json").read_text(encoding="utf-8"))
CASES = GOLDEN["transitions"]

S3 = LedMatrixSpec(12, 5, "3x5")


def lay(message: str, **options):
    return layout_message(message, S3, LedLayoutOptions(**options))


def _diff(actual: bytes, expected: bytes, width: int, limit: int = 6) -> str:
    out = []
    for p in range(min(len(actual), len(expected)) // 3):
        got, want = actual[p * 3 : p * 3 + 3], expected[p * 3 : p * 3 + 3]
        if got != want:
            out.append(f"  ({p % width}, {p // width}): got #{got.hex()} want #{want.hex()}")
            if len(out) == limit:
                break
    return "\n".join(out)


def _golden_plan(case: dict):
    """Resolve, lay out and plan a golden case exactly as FiestaUI's generator does."""
    plugin = None
    if "pluginModel" in case:
        plugin = {**case["pluginModel"], "charset": materialize_character_set(case["pluginModel"]["charset"])}
    model = plugin or (MODELS[case["model"]] if "model" in case else None)
    choice = case["transition"]
    if isinstance(choice, dict):
        choice = LedTransitionSpec.from_dict(choice)
    spec = resolve_led_transition(choice, model).spec if model else choice
    raw = case.get("options", {})
    options = LedLayoutOptions(
        text_color=raw.get("textColor"),
        monochrome=raw.get("monochrome"),
        letter_case=raw.get("letterCase", "upper"),
        charset=plugin["charset"] if plugin else None,
    )
    s = case["spec"]
    grid_spec = LedMatrixSpec(s["width"], s["height"], s.get("font", "5x7"))
    before = layout_message(case["from"], grid_spec, options)
    after = layout_message(case["to"], grid_spec, options)
    return spec, before, after, plan_transition(before, after, spec)


# --- golden sequences -------------------------------------------------------


def test_golden_has_the_nine_transition_cases():
    assert len(CASES) == 9
    assert {"pixoo 32-frame budget", "acme sign 12-frame budget, own charset"} <= {c["name"] for c in CASES}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_resolved_spec_matches_fiestaui(case):
    spec, *_ = _golden_plan(case)
    resolved = spec if isinstance(spec, str) else spec.to_dict()
    assert resolved == case["resolvedSpec"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_duration_and_frame_count_match_fiestaui(case):
    *_, tr = _golden_plan(case)
    assert (tr.duration_ms, tr.frame_count) == (case["durationMs"], case["frameCount"])


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_every_frame_matches_fiestaui_byte_for_byte(case):
    *_, tr = _golden_plan(case)
    frames = transition_frames(tr, case.get("fps", 30))
    expected = [base64.b64decode(f) for f in case["frames"]]
    assert len(frames) == len(expected)
    for i, (frame, want) in enumerate(zip(frames, expected, strict=True)):
        assert (frame.width, frame.height) == (case["width"], case["height"])
        assert frame.pixels == want, f"frame {i} of {len(expected)} differs:\n" + _diff(frame.pixels, want, frame.width)


def test_pixoo_budget_is_exactly_32_frames_ending_on_the_target():
    case = next(c for c in CASES if c["name"] == "pixoo 32-frame budget")
    *_, after, tr = _golden_plan(case)
    frames = transition_frames(tr)
    assert len(frames) == 32
    assert frames[-1].pixels == rasterize(after).pixels


def test_acme_sign_scrambles_only_through_its_own_set_and_shows_its_euro():
    case = next(c for c in CASES if c["name"] == "acme sign 12-frame budget, own charset")
    spec, before, after, tr = _golden_plan(case)
    charset = before.options.charset
    assert charset is not None and charset["id"] == "acme_sign_v1"
    pool = set(scramble_pool(charset))
    seen = set()
    step = spec.step_ms
    for f in range(1, tr.frame_count - 1):
        layout = tr.layout_at(f * step)
        for i, cell in enumerate(layout.cells):
            if cell.glyph in (before.cells[i].glyph, after.cells[i].glyph):
                continue
            assert cell.glyph in pool, (f, i, cell.glyph)
            seen.add(cell.glyph)
    for glyph in seen:
        if glyph.startswith("icon:"):
            assert glyph[5:] in charset["icons"]
        elif not glyph.startswith("tile:"):
            assert glyph in charset["chars"]
    assert "€" in seen


# --- the flip ---------------------------------------------------------------


def test_flip_runs_scramble_then_target_within_the_stagger():
    tr = plan_transition(lay("AB"), lay("CD"), LedTransitionSpec("flip", step_ms=10, scramble_steps=4, stagger=2))
    assert tr.duration_ms == (2 + 4 + 1) * 10
    assert tr.frame_at(0).pixels == tr.from_frame.pixels
    assert tr.frame_at(tr.duration_ms).pixels == tr.to_frame.pixels


def test_flip_is_deterministic():
    spec = LedTransitionSpec("flip", step_ms=10, half_flap=False)
    wide = LedMatrixSpec(24, 5, "3x5")

    def frames(before, after):
        return [
            f.pixels
            for f in transition_frames(plan_transition(layout_message(before, wide), layout_message(after, wide), spec))
        ]

    a = frames("AB 12", "CD 99")
    assert a == frames("AB 12", "CD 99")
    # A different change scrambles differently.
    c = frames("AB 12", "CD 98")
    assert a != c


def test_flip_path_does_not_depend_on_character_order():
    ab = plan_transition(lay("A"), lay("B"), LedTransitionSpec("flip", step_ms=10, stagger=0))
    az = plan_transition(lay("A"), lay("Z"), LedTransitionSpec("flip", step_ms=10, stagger=0))
    assert ab.duration_ms == az.duration_ms


def test_built_in_pool_holds_only_what_the_set_draws():
    pool3 = scramble_pool(BUILTIN_CHARACTER_SETS["led_3x5"])
    pool5 = scramble_pool(BUILTIN_CHARACTER_SETS["led_5x7"])
    assert " " not in pool3
    for glyph in pool3:
        if glyph.startswith("icon:"):
            assert glyph[5:] in BUILTIN_CHARACTER_SETS["led_3x5"]["icons"]
        elif not glyph.startswith("tile:"):
            assert glyph in BUILTIN_CHARACTER_SETS["led_3x5"]["chars"]
    assert len(pool5) > len(pool3)
    assert "a" in pool3 and any(g.startswith("tile:") for g in pool3) and any(g.startswith("icon:") for g in pool3)


def test_a_sets_own_characters_are_in_its_pool_before_any_layout_draws_them():
    acme = GOLDEN["layouts"][7]["charset"]
    set_ = materialize_character_set(
        {**acme, "id": "acme_sign_yen", "chars": ["A", "B", "¥"], "glyphs": {"¥": ["#.#", ".#.", "###", ".#.", ".#."]}}
    )
    pool = scramble_pool(set_)
    assert "¥" in pool
    assert len(pool) == 3 + 7 + len(set_["icons"])


def test_without_a_set_the_faces_built_in_set_is_the_pool():
    plain = plan_transition(lay("A"), lay("B"), LedTransitionSpec("flip", step_ms=10, stagger=0))
    face_pool = set(scramble_pool(BUILTIN_CHARACTER_SETS["led_3x5"]))
    for t in range(10, plain.duration_ms, 10):
        assert plain.layout_at(t).cells[0].glyph in face_pool


def test_half_flap_shows_the_next_glyph_on_top_of_the_current():
    tr = plan_transition(lay("A"), lay("B"), LedTransitionSpec("flip", step_ms=80, stagger=0, scramble_steps=2))
    whole, half = tr.frame_at(80), tr.frame_at(120)
    assert tr.frame_count is None
    assert whole.pixels != half.pixels
    # The bottom rows (below the top ceil(5/2) = 3) are still the current glyph.
    assert frame_to_ascii(whole).split("\n")[3:] == frame_to_ascii(half).split("\n")[3:]


def test_coarse_flip_is_whole_frames_only():
    tr = plan_transition(lay("A"), lay("B"), LedTransitionSpec("flip", step_ms=80, stagger=0, half_flap=False))
    assert tr.frame_count == 6 + 2
    assert tr.frame_at(120).pixels == tr.frame_at(80).pixels


def test_flip_fits_a_budget_by_shortening_stagger_then_scramble():
    tr = plan_transition(
        lay("A"), lay("?"), LedTransitionSpec("flip", step_ms=80, scramble_steps=20, stagger=10, max_frames=8)
    )
    assert (tr.frame_count, tr.duration_ms) == (8, 7 * 80)
    frames = transition_frames(tr)
    assert len(frames) == 8
    assert frames[0].pixels == tr.from_frame.pixels and frames[7].pixels == tr.to_frame.pixels
    for f in range(8):
        assert tr.frame_at(f * 80 + 10).pixels == frames[f].pixels
    assert plan_transition(lay("AB"), lay("CD"), LedTransitionSpec("flip", max_frames=32)).frame_count == 14
    two = plan_transition(lay("A"), lay("B"), LedTransitionSpec("flip", max_frames=2))
    assert [f.pixels for f in transition_frames(two)] == [two.from_frame.pixels, two.to_frame.pixels]


@pytest.mark.parametrize("kind", LED_TRANSITION_KINDS)
def test_budgeted_frames_are_indexed_exactly(kind):
    for n in range(3, 33):
        tr = plan_transition(
            lay("AB"), lay("CA"), LedTransitionSpec(kind, duration_ms=777, max_frames=n, scramble_steps=30, stagger=10)
        )
        frames = transition_frames(tr)
        assert len(frames) == tr.frame_count
        assert frames[-1].pixels == tr.to_frame.pixels
        hold = tr.duration_ms / (tr.frame_count - 1)
        for f in range(tr.frame_count):
            assert tr.frame_at(f * hold).pixels == frames[f].pixels, (kind, n, f)
            assert tr.frame_at_index(f).pixels == frames[f].pixels, (kind, n, f)


def test_snaps_between_different_sizes_and_grids():
    big = layout_message("A", LedMatrixSpec(24, 5, "3x5"))
    assert plan_transition(lay("A"), big, LedTransitionSpec("fade")).duration_ms == 0
    other_grid = layout_message("A", LedMatrixSpec(12, 5, "5x7"))
    assert plan_transition(lay("A"), other_grid, LedTransitionSpec("flip")).duration_ms == 0
    assert plan_transition(lay("A"), lay("A"), "flip").duration_ms == 0


# --- cascade and per-pixel kinds --------------------------------------------


def test_cascade_flips_changed_cells_in_reading_order_and_snaps_colour_only_changes():
    tr = plan_transition(lay("AB"), lay("CD"), LedTransitionSpec("cascade", duration_ms=200))
    assert tr.duration_ms == 200
    assert tr.layout_at(150).cells[0].glyph == "C" and tr.layout_at(150).cells[1].glyph == "B"
    assert plan_transition(lay("A"), lay("{red:A}"), "cascade").duration_ms == 0


def test_cascade_gives_every_cell_a_minimum_slot():
    tr = plan_transition(lay("ABC"), lay("XYZ"), LedTransitionSpec("cascade", duration_ms=30))
    assert tr.duration_ms == 3 * 32


def test_wipe_reveals_from_the_left_and_fade_blends():
    wipe = plan_transition(lay("A"), lay("{63}"), LedTransitionSpec("wipe", duration_ms=120))
    mid = wipe.frame_at(60)  # p = 1/2: edge at x = 6
    assert mid.pixels[: 6 * 3] == wipe.to_frame.pixels[: 6 * 3]
    assert mid.pixels[6 * 3 : 12 * 3] == wipe.from_frame.pixels[6 * 3 : 12 * 3]
    fade = plan_transition(lay("{63}"), lay("{67}"), LedTransitionSpec("fade", duration_ms=100))
    half = fade.frame_at(50)
    assert tuple(half.pixels[:3]) == (0x9A, 0x68, 0x86)  # (eb+4a)/2, (40+90)/2, (34+d9)/2, half-to-even


def test_slide_pushes_the_old_frame_up():
    tr = plan_transition(lay("A"), lay("B"), LedTransitionSpec("slide", duration_ms=100))
    mid = tr.frame_at(40)  # shift = round(0.4 * 5) = 2
    w = 12 * 3
    assert mid.pixels[:w] == tr.from_frame.pixels[2 * w : 3 * w]


def test_dissolve_switches_a_growing_set_of_pixels():
    tr = plan_transition(lay("{63}{63}{63}"), lay("{67}{67}{67}"), LedTransitionSpec("dissolve", duration_ms=100))

    def switched(t):
        f = tr.frame_at(t)
        return sum(1 for i in range(0, len(f.pixels), 3) if f.pixels[i : i + 3] != tr.from_frame.pixels[i : i + 3])

    assert 0 < switched(30) < switched(70) <= 45


# --- the transition menu ----------------------------------------------------


def test_menu_has_none_beside_every_kind():
    assert set(LED_TRANSITIONS) == {"none", *LED_TRANSITION_KINDS}


def test_streamed_device_is_judged_by_push_rate():
    fast = {"delivery": "stream", "maxFps": 60}
    assert transition_spec_for_device("flip", fast).spec == LedTransitionSpec("flip")
    slow = {**fast, "maxFps": 10}
    result = transition_spec_for_device("flip", slow)
    assert result.spec == LedTransitionSpec("flip", step_ms=100, half_flap=False) and result.degraded
    assert transition_spec_for_device("slide", slow).spec == LedTransitionSpec("slide")
    crawl = {**fast, "maxFps": 2}
    assert transition_spec_for_device("flip", crawl) is None
    assert transition_spec_for_device("none", crawl).spec == "none"


def test_sequence_player_is_judged_by_its_budget():
    pixoo = MODELS["divoom_pixoo64"]["animation"]
    flip = transition_spec_for_device("flip", pixoo)
    assert flip.spec == LedTransitionSpec("flip", step_ms=80, half_flap=False, max_frames=32) and flip.degraded
    assert transition_spec_for_device("fade", pixoo).spec == LedTransitionSpec("fade", max_frames=32)
    tiny = {**pixoo, "maxFrames": 4}
    assert transition_spec_for_device("flip", tiny) is None
    assert transition_spec_for_device("fade", tiny) is not None


def test_menu_per_model_with_reasons():
    awtrix = transitions_for_model(MODELS["ulanzi_tc001_awtrix"])
    assert [a.id for a in awtrix if a.available] == ["none"]
    assert "unmeasured" in next(a for a in awtrix if a.id == "flip").reason
    assert [a.id for a in transitions_for_model(MODELS["vestaboard_note"]) if a.available] == ["none"]
    hub = transitions_for_model(MODELS["hub75_64x32"])
    assert all(a.available and not a.degraded for a in hub)
    pixoo = transitions_for_model(MODELS["divoom_pixoo64"])
    assert all(a.available for a in pixoo)
    assert all(a.degraded and "32 frames" in a.reason for a in pixoo if a.id != "none")


def test_default_is_flip_when_the_device_can_show_it_else_none():
    assert default_transition_id_for_model(MODELS["hub75_128x64"]) == "flip"
    assert default_transition_id_for_model(MODELS["divoom_pixoo64"]) == "flip"
    assert default_transition_id_for_model(MODELS["ulanzi_tc001_awtrix"]) == "none"
    assert default_transition_id_for_model(MODELS["vestaboard_flagship"]) == "none"


def test_resolve_precedence_explicit_then_default_with_fallback_reasons():
    hub = MODELS["hub75_64x32"]
    r = resolve_led_transition(None, hub)
    assert (r.id, r.source) == ("flip", "default")
    r = resolve_led_transition("slide", hub)
    assert (r.id, r.spec, r.source) == ("slide", LedTransitionSpec("slide"), "explicit")
    r = resolve_led_transition("none", hub)
    assert (r.id, r.spec, r.source) == ("none", "none", "explicit")
    fell = resolve_led_transition("slide", MODELS["ulanzi_tc001_awtrix"])
    assert (fell.id, fell.spec, fell.source, fell.requested) == ("none", "none", "fallback", "slide")
    assert "frames a second" in fell.reason
    pixoo = MODELS["divoom_pixoo64"]
    r = resolve_led_transition(LedTransitionSpec("flip", step_ms=120, half_flap=True), pixoo)
    assert r.spec == LedTransitionSpec("flip", step_ms=120, half_flap=False, max_frames=32)
    assert r.source == "explicit" and "32 frames" in r.reason
    assert resolve_led_transition(LedTransitionSpec("flip", step_ms=20), pixoo).spec.step_ms == 80
    slow = {**hub, "animation": {**hub["animation"], "maxFps": 10}}
    r = resolve_led_transition(LedTransitionSpec("flip", step_ms=40, half_flap=True), slow)
    assert r.spec == LedTransitionSpec("flip", step_ms=100, half_flap=False)
    assert "no half-flaps" in r.reason
    r = resolve_led_transition("wipe")
    assert (r.id, r.spec, r.source) == ("wipe", LedTransitionSpec("wipe"), "explicit")
    r = resolve_led_transition(None)
    assert (r.id, r.spec, r.source) == ("none", "none", "default")
