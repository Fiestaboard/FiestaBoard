"""Which transition a device runs: the menu, its requirements and the selection rule.

A port of FiestaUI's ``src/lib/led-transition-registry.ts`` (d4e3074), reason
strings included. The flip is one entry in a menu that always contains
"none". Each entry declares what it needs (a frame rate for a streamed
device, a frame count for one that plays an uploaded sequence), so a device
model can say which entries it can run, and a choice it cannot honour falls
back to the model's default with a reason.

Selection precedence (:func:`resolve_led_transition`): an explicit choice
(board or page setting), else the model's default, which is flip when the
device can show one and none otherwise. The coarse, budgeted flip is not an
entry: it is what "flip" becomes on a device that shows one frame per step,
or only N frames in all.

Device models are FiestaUI ``DeviceModel`` documents (dicts). Only the
``animation`` capability is read: ``delivery`` (stream / sequence / none),
``maxFps``, ``maxFrames``, ``minFrameMs``. There is no built-in-id lookup
here; the caller resolves a model id to its document.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal

from .transitions import DEFAULT_LED_FLIP_STEP_MS, LedTransitionSpec

__all__ = [
    "LED_TRANSITIONS",
    "SPLIT_FLAP_REASON",
    "LedTransitionAvailability",
    "LedTransitionEntry",
    "LedTransitionId",
    "ResolvedLedTransition",
    "TransitionForDevice",
    "default_transition_id_for_model",
    "is_led_transition_id",
    "resolve_led_transition",
    "transition_spec_for_device",
    "transitions_for_model",
    "unknown_transition_reason",
]

LedTransitionId = Literal["none", "flip", "cascade", "slide", "wipe", "fade", "dissolve"]


@dataclass(frozen=True)
class LedTransitionEntry:
    """One menu entry and what it needs to look as intended."""

    id: LedTransitionId
    label: str
    description: str
    #: A streamed device's push rate (or a sequence's playback rate) needed at all.
    min_fps: float
    #: The rate at which the entry has every frame it wants (a flip's half-flaps).
    full_fps: float
    #: The smallest sequence budget that still reads as this transition.
    min_frames: int
    #: How it fits a frame budget: shorten (flip), sample (continuous), or nothing.
    budget: Literal["subsample", "quantise", "none"]


def _entry(id_, label, description, min_fps, full_fps, min_frames, budget) -> LedTransitionEntry:
    return LedTransitionEntry(id_, label, description, min_fps, full_fps, min_frames, budget)


LED_TRANSITIONS: Mapping[str, LedTransitionEntry] = {
    "none": _entry(
        "none", "None — change instantly", "The new message replaces the old one in a single frame.", 0, 0, 1, "none"
    ),
    "flip": _entry(
        "flip",
        "Flip",
        "Every changing cell scrambles through glyphs from the board's own character set, then lands on its new "
        "one — FiestaBoard's take on the split-flap cascade.",
        5,
        25,
        8,
        "subsample",
    ),
    "cascade": _entry("cascade", "Cascade", "One flip per changed cell, in reading order.", 5, 30, 6, "quantise"),
    "slide": _entry(
        "slide", "Slide", "The new message pushes the old one up and off the panel.", 5, 30, 6, "quantise"
    ),
    "wipe": _entry("wipe", "Wipe", "A curtain reveals the new message from left to right.", 5, 30, 6, "quantise"),
    "fade": _entry("fade", "Fade", "The old message dims as the new one brightens.", 5, 30, 4, "quantise"),
    "dissolve": _entry(
        "dissolve", "Dissolve", "Pixels switch from old to new in a scattered order.", 5, 30, 4, "quantise"
    ),
}


@dataclass(frozen=True)
class TransitionForDevice:
    """What a device would run for an entry: the spec with cadence and budget applied."""

    spec: LedTransitionSpec | Literal["none"]
    degraded: bool
    reason: str | None = None


@dataclass(frozen=True)
class LedTransitionAvailability:
    id: LedTransitionId
    entry: LedTransitionEntry
    available: bool
    #: Why it is unavailable, or how it is degraded when it is.
    reason: str | None
    spec: LedTransitionSpec | Literal["none"] | None
    degraded: bool


@dataclass(frozen=True)
class ResolvedLedTransition:
    id: LedTransitionId
    #: The spec to plan with, or ``"none"`` to snap.
    spec: LedTransitionSpec | Literal["none"]
    source: Literal["explicit", "default", "fallback"]
    #: The explicit choice set aside, when ``source`` is ``fallback``: an id
    #: the device cannot run, or a value that is no id at all (a stale
    #: setting), reported as given.
    requested: str | None = None
    reason: str | None = None


def _js(value: object) -> str:
    """A number (or a missing value) as a JavaScript template literal prints it."""
    if value is None:
        return "undefined"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def transition_spec_for_device(transition_id: str, animation: Mapping) -> TransitionForDevice | None:
    """The spec a device would run for an entry, or ``None`` when it cannot run it.

    - ``delivery: "none"`` runs only "none".
    - A **sequence** player is judged by its frame budget (``maxFrames`` >=
      the entry's ``min_frames``); a flip becomes one frame per step with no
      half-flaps, and everything is compressed to ``maxFrames``.
    - A **streamed** device is judged by ``maxFps``; a flip below the entry's
      ``full_fps`` is coarse (one frame per step).
    """
    if transition_id == "none":
        return TransitionForDevice("none", False)
    entry = LED_TRANSITIONS[transition_id]
    delivery = animation.get("delivery")
    if delivery == "none":
        return None
    if delivery == "sequence":
        budget = animation.get("maxFrames")
        if budget is not None and budget < entry.min_frames:
            return None
        min_frame_ms = animation.get("minFrameMs")
        step_ms = max(DEFAULT_LED_FLIP_STEP_MS, DEFAULT_LED_FLIP_STEP_MS if min_frame_ms is None else min_frame_ms)
        flip = transition_id == "flip"
        spec = LedTransitionSpec("flip", step_ms=step_ms, half_flap=False) if flip else LedTransitionSpec(transition_id)
        if budget is not None:
            spec = replace(spec, max_frames=budget)
            reason = (
                f"Compressed to {_js(budget)} frames: one frame per step, no half-flaps"
                if flip
                else f"Compressed to {_js(budget)} frames"
            )
        else:
            reason = "One frame per step, no half-flaps" if flip else None
        return TransitionForDevice(spec, reason is not None, reason)
    max_fps = animation.get("maxFps", 0)
    if max_fps < entry.min_fps:
        return None
    if transition_id == "flip" and max_fps < entry.full_fps:
        step_ms = max(DEFAULT_LED_FLIP_STEP_MS, math.ceil(1000 / max_fps))
        return TransitionForDevice(
            LedTransitionSpec("flip", step_ms=step_ms, half_flap=False),
            True,
            f"{step_ms} ms per step, no half-flaps: the device pushes about {_js(max_fps)} frames a second",
        )
    return TransitionForDevice(LedTransitionSpec(transition_id), False)


#: Why no LED transition applies to a split-flap board. Its frames are
#: written one at a time and its own flap cascade animates every change: the
#: menu is not a matter of push rate there.
SPLIT_FLAP_REASON = "A split-flap board animates each change with its own flap cascade; LED transitions do not apply."


def is_led_transition_id(value: object) -> bool:
    """Whether *value* is a menu id (FiestaUI ``isLedTransitionId``): its own key, nothing inherited."""
    return isinstance(value, str) and value in LED_TRANSITIONS


def unknown_transition_reason(requested: str) -> str:
    """Why a value that is no menu id fell back (FiestaUI's wording)."""
    return f'Unknown transition "{requested}"; one of {", ".join(LED_TRANSITIONS)}.'


def _unavailable_reason(transition_id: str, animation: Mapping) -> str:
    entry = LED_TRANSITIONS[transition_id]
    delivery = animation.get("delivery")
    if delivery == "none":
        return "This device takes one message, not frames; it changes by itself."
    if delivery == "sequence":
        return (
            f"Needs at least {entry.min_frames} frames; this device plays sequences of up to "
            f"{_js(animation.get('maxFrames'))}."
        )
    return (
        f"Needs about {_js(entry.min_fps)} frames a second; this device's push rate is {_js(animation.get('maxFps'))}."
    )


def transitions_for_model(model: Mapping) -> list[LedTransitionAvailability]:
    """The whole menu judged against a device model. "none" is always available.

    A split-flap board runs "none" only, whatever its frame rate says: the
    flap cascade is the animation.
    """
    animation = model["animation"]
    flap = model.get("technology") == "split_flap"
    out = []
    for transition_id, entry in LED_TRANSITIONS.items():
        if flap and transition_id != "none":
            out.append(LedTransitionAvailability(transition_id, entry, False, SPLIT_FLAP_REASON, None, False))
            continue
        result = transition_spec_for_device(transition_id, animation)
        if result is None:
            reason = _unavailable_reason(transition_id, animation)
            out.append(LedTransitionAvailability(transition_id, entry, False, reason, None, False))
        else:
            out.append(
                LedTransitionAvailability(transition_id, entry, True, result.reason, result.spec, result.degraded)
            )
    return out


def default_transition_id_for_model(model: Mapping) -> LedTransitionId:
    """Flip when the device can show one; otherwise none. Nothing else is ever a default.

    A split-flap board's default is always none: its flap cascade is the animation.
    """
    if model.get("technology") == "split_flap":
        return "none"
    return "flip" if transition_spec_for_device("flip", model["animation"]) else "none"


def resolve_led_transition(
    choice: LedTransitionId | LedTransitionSpec | None, model: Mapping | None = None
) -> ResolvedLedTransition:
    """Apply the precedence: an explicit choice the device can run, else the model's default.

    A spec with its own timings keeps them, but never past what the device can
    show: a slow stream still drops the half-flap, a sequence player holds each
    frame at least its minimum, and a frame budget always applies (the tighter
    of the caller's and the device's). Without a model, an explicit choice runs
    as written and the default is none. A choice that is no menu id at all (a
    stale setting, a typo in a plugin's request) is never run or looked up: it
    falls back to the default with ``source="fallback"``, ``requested`` as
    given and a reason. A split-flap board runs only "none".
    """
    requested = None if choice is None else choice if isinstance(choice, str) else choice.kind
    if requested is not None and not is_led_transition_id(requested):
        fallback_id = "none" if model is None else default_transition_id_for_model(model)
        fallback = "none" if model is None else transition_spec_for_device(fallback_id, model["animation"]).spec
        return ResolvedLedTransition(
            fallback_id, fallback, "fallback", requested=requested, reason=unknown_transition_reason(requested)
        )
    if model is None:
        if choice is None or choice == "none":
            return ResolvedLedTransition("none", "none", "explicit" if choice else "default")
        spec = LedTransitionSpec(choice) if isinstance(choice, str) else choice
        return ResolvedLedTransition(requested, spec, "explicit")
    animation = model["animation"]
    if requested is not None:
        if model.get("technology") == "split_flap" and requested != "none":
            return ResolvedLedTransition("none", "none", "fallback", requested=requested, reason=SPLIT_FLAP_REASON)
        result = transition_spec_for_device(requested, animation)
        if result is not None:
            spec = result.spec
            if isinstance(choice, LedTransitionSpec) and result.spec != "none":
                device = result.spec
                spec = choice
                if device.step_ms is not None:
                    own = DEFAULT_LED_FLIP_STEP_MS if choice.step_ms is None else choice.step_ms
                    spec = replace(spec, step_ms=max(own, device.step_ms))
                if device.half_flap is False:
                    spec = replace(spec, half_flap=False)
                if device.max_frames is not None:
                    own_budget = device.max_frames if choice.max_frames is None else choice.max_frames
                    spec = replace(spec, max_frames=min(own_budget, device.max_frames))
            return ResolvedLedTransition(requested, spec, "explicit", reason=result.reason)
        fallback_id = default_transition_id_for_model(model)
        fallback = transition_spec_for_device(fallback_id, animation)
        return ResolvedLedTransition(
            fallback_id,
            fallback.spec,
            "fallback",
            requested=requested,
            reason=_unavailable_reason(requested, animation),
        )
    default_id = default_transition_id_for_model(model)
    result = transition_spec_for_device(default_id, animation)
    return ResolvedLedTransition(default_id, result.spec, "default", reason=result.reason)
