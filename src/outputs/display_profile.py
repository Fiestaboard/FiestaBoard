"""What a display can draw, handed to data plugins as ``self.board.display``.

An output plugin already declares its device: the FiestaUI device model
(technology, colour) and the character set it draws with (lowercase, coloured
text, highlighted backgrounds, colour tiles, icons). Core resolves both per
board. This module turns that resolution into one read-only
:class:`DisplayProfile` and passes it down the same path the render's
``extended_markup`` switch already travels, so a data plugin can ask what the
board in front of it can show instead of assuming a Vestaboard.

The profile is derived, never configured: a new output plugin (or a new
device model) is described to every data plugin by what it declares, with no
change to any data plugin. ``self.board.display`` is ``None`` wherever no
board is in hand (unit tests, a size-only preview), and a plugin must treat
``None`` as "assume the split-flap baseline".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.led.charsets import resolve_character_set, validate_message
from src.markup import BOARD_ICONS

from .board_profile import board_character_set, board_device_model, led_layout_choice
from .cells import extended_markup_kw, output_character_set

#: The colour names extended markup accepts, in the order a prompt lists them.
SPAN_COLORS: tuple[str, ...] = ("red", "orange", "yellow", "green", "blue", "violet", "white", "black")

#: The features :meth:`DisplayProfile.supports` answers for.
FEATURES: frozenset[str] = frozenset({"lowercase", "color_text", "background", "tiles", "icons", "rgb", "solid_shapes"})


@dataclass(frozen=True)
class DisplayProfile:
    """The display a plugin is rendering for, as its output plugin declares it.

    Attributes:
        technology: ``"split_flap"``, ``"led_matrix"``, ``"screen"`` or
            ``"unknown"`` (the FiestaUI device model's ``technology``).
        device_model: The FiestaUI device model id, e.g. ``"divoom_pixoo64"``.
        charset: The character set id the board draws with, e.g. ``"led_3x5"``.
        color: ``"tiles"`` (a flap's fixed colours), ``"rgb"`` or ``"mono"``.
        mixed_case: Lowercase draws as lowercase (else it is upper-cased).
        color_spans: ``{red:HOT}`` draws coloured text.
        block_spans: ``{black/yellow:AQI}`` draws text on a coloured background.
        tiles: ``{red}`` / ``{63}`` draw solid colour tiles.
        icons: Icon names ``{icon:<name>}`` draws as a glyph on this board.
        chars: Every character the board draws.
        tile_gap: LED tile style: ``"fill"`` joins same-coloured neighbours
            into solid shapes, ``"gap"`` keeps a dark gutter; ``None`` off LED.
    """

    technology: str = "split_flap"
    device_model: str | None = None
    charset: str | None = None
    color: str = "tiles"
    mixed_case: bool = False
    color_spans: bool = False
    block_spans: bool = False
    tiles: bool = True
    icons: tuple[str, ...] = ()
    chars: str = ""
    tile_gap: str | None = None

    @property
    def key(self) -> str:
        """Identity for caches: two boards with equal keys draw identically."""
        return "|".join(
            str(part) for part in (self.device_model or self.technology, self.charset, self.color, self.tile_gap)
        )

    def supports(self, feature: str) -> bool:
        """Whether this display can draw *feature* (one of :data:`FEATURES`).

        ``"solid_shapes"`` means same-coloured tiles join into one filled area
        (an LED board in the seamless tile style). An unknown feature name is
        a programming error and raises ``ValueError``.
        """
        if feature not in FEATURES:
            raise ValueError(f"Unknown display feature {feature!r}; one of {sorted(FEATURES)}")
        return {
            "lowercase": self.mixed_case,
            "color_text": self.color_spans,
            "background": self.block_spans,
            "tiles": self.tiles,
            "icons": bool(self.icons),
            "rgb": self.color == "rgb",
            "solid_shapes": self.tiles and self.tile_gap == "fill",
        }[feature]

    def check(self, text: str) -> list[dict[str, Any]]:
        """What in *text* (board markup) this display cannot draw.

        One entry per problem: ``{row, col, reason, fallback}``, where
        ``fallback`` is what the board shows instead. Empty when every cell
        draws as written. Uses the same validation as the template editor's
        warnings, so a plugin and the editor never disagree.
        """
        if not self.charset:
            return []
        try:
            result = validate_message(text, self.charset)
        except (KeyError, ValueError):
            return []
        return [
            {k: v for k, v in issue.to_dict().items() if k in ("row", "col", "reason", "fallback")}
            for issue in result.issues
        ]

    def ai_brief(self) -> str:
        """Plain-language rules for a model writing board markup for this display.

        Generated from the profile, so it lists exactly the markup this board
        draws and nothing it does not. A split-flap board gets the same
        uppercase-and-tiles rules a Vestaboard always had.
        """
        kind = {
            "split_flap": "a split-flap board",
            "led_matrix": {
                "rgb": "a full-colour LED pixel display",
                "mono": "a single-colour LED pixel display",
            }.get(self.color, "an LED pixel display"),
            "screen": "a screen",
        }.get(self.technology, "a display board")
        lines = [f"THE DISPLAY: {kind}."]
        if self.mixed_case:
            lines.append("Lowercase is drawn as lowercase: write normal sentence case, not all caps.")
        else:
            lines.append("It has no lowercase: everything is shown in CAPITALS.")
        names = ", ".join(SPAN_COLORS)
        if self.color_spans:
            lines.append(
                "Coloured text: wrap words as {colour:text}, e.g. {green:63F} or {red:Delayed}. "
                f"Colours: {names}."
                + (" Any #rrggbb hex colour works too, e.g. {#ff8800:Sunset}." if self.color == "rgb" else "")
            )
        if self.block_spans:
            lines.append(
                "Highlighted text: {background/text colour:words} draws the words on a coloured band, "
                "e.g. {yellow/black:AQI 160}. Use it for the one thing that needs attention."
            )
        if self.tiles:
            tile = "Solid colour squares: {red}, {green} and the other colour names each draw one block."
            if self.supports("solid_shapes"):
                tile += " Neighbouring blocks of the same colour join into one solid shape, so rows of them draw bars and filled areas."
            lines.append(tile)
        if self.icons:
            lines.append("Icons: {icon:name} draws a small picture. Available: " + ", ".join(self.icons) + ".")
        if not (self.color_spans or self.block_spans):
            lines.append("Colour comes only from the solid squares; text itself is one colour.")
        if self.chars:
            symbols = "".join(ch for ch in self.chars if not ch.isalnum() and ch != " ")
            if symbols:
                lines.append(f"Punctuation it draws: {' '.join(symbols)}. Anything else shows as a blank.")
        return "\n".join(lines)


def _model_of(client: Any) -> Mapping[str, Any] | None:
    plugin = getattr(client, "plugin", None)
    model = getattr(plugin, "device_model", None) if plugin is not None else None
    return model if isinstance(model, Mapping) else None


def _charset_of(client: Any, model: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    charset = output_character_set(client)
    if charset is not None:
        return charset
    ref = model.get("charset") if model else None
    if isinstance(ref, Mapping):
        return ref
    if isinstance(ref, str):
        try:
            resolved = resolve_character_set(ref)
        except (KeyError, ValueError):
            return None
        return resolved if isinstance(resolved, Mapping) else None
    return None


def _profile(
    model: Mapping[str, Any], charset: Mapping[str, Any] | None, config: Mapping[str, Any] | None
) -> DisplayProfile:
    """One :class:`DisplayProfile` from a resolved device model, character
    set and the board's output config (for the LED tile style)."""
    charset = charset or {}
    color = model.get("color")
    color_kind = color.get("kind") if isinstance(color, Mapping) else None
    # The tile style the device is actually drawn with: the board's choice
    # resolved against what its model allows (the preview uses the same).
    layout = led_layout_choice(model, config)
    icons = charset.get("icons") or ()
    chars = charset.get("chars") or ()
    return DisplayProfile(
        technology=str(model.get("technology") or "unknown"),
        device_model=str(model.get("id")) if model.get("id") else None,
        charset=str(charset.get("id")) if charset.get("id") else None,
        # FiestaUI's colour kinds are "rgb", "monochrome" and "tiles" (device-model schema).
        color="rgb" if color_kind == "rgb" else ("mono" if color_kind == "monochrome" else "tiles"),
        mixed_case=bool(charset.get("mixedCase")),
        color_spans=bool(charset.get("colorSpans")),
        block_spans=bool(charset.get("blockSpans")),
        tiles=bool(charset.get("tiles", True)),
        icons=tuple(str(i) for i in icons if str(i) in BOARD_ICONS),
        chars="".join(str(c) for c in chars),
        tile_gap=layout.tile_gap if layout is not None else None,
    )


def display_profile_for_client(client: Any) -> DisplayProfile | None:
    """The :class:`DisplayProfile` of the board behind *client* (a board's
    output driver), or ``None`` when the driver does not describe its device
    (a test double, a legacy client).
    """
    model = _model_of(client)
    if model is None:
        return None
    config = getattr(getattr(client, "plugin", None), "config", None)
    return _profile(model, _charset_of(client, model), config if isinstance(config, Mapping) else None)


def display_profile_for_board(board: Mapping[str, Any]) -> DisplayProfile | None:
    """The :class:`DisplayProfile` of a board's settings entry, resolved the
    way previews resolve it (:mod:`src.outputs.board_profile`); ``None`` when
    the board's device model is unknown (its output plugin is not installed).
    """
    model = board_device_model(board)
    if not isinstance(model, Mapping):
        return None
    config = board.get("output_config")
    return _profile(model, board_character_set(board), config if isinstance(config, Mapping) else None)


def render_kw(client: Any) -> dict[str, Any]:
    """Every page/template render keyword for the board behind *client*:
    :func:`~src.outputs.cells.extended_markup_kw`, plus ``display`` (the
    board's :class:`DisplayProfile`) when its driver describes its device.
    """
    kw = dict(extended_markup_kw(client))
    profile = display_profile_for_client(client)
    if profile is not None:
        kw["display"] = profile
    return kw
