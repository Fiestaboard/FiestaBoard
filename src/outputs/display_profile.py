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
FEATURES: frozenset[str] = frozenset(
    {"lowercase", "color_text", "background", "tiles", "icons", "rgb", "solid_shapes", "pixels"}
)


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
        font: The LED face the board draws text in: ``"5x7"`` (Large) or
            ``"3x5"`` (Small); ``None`` off LED. A board's face can change
            at runtime (its text size setting), and its grid with it.
        rows: The board's grid height in characters, when known.
        cols: The board's grid width in characters, when known.
        width: A pixel-matrix board's width in pixels; ``None`` on any
            other board. With ``height`` it is what ``supports("pixels")``
            answers: the board draws a page's pixel canvases.
        height: A pixel-matrix board's height in pixels; ``None`` otherwise.
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
    font: str | None = None
    rows: int | None = None
    cols: int | None = None
    width: int | None = None
    height: int | None = None

    @property
    def key(self) -> str:
        """Identity for caches: two boards with equal keys draw identically.

        The grid is not part of it (a cache keys on the board's size beside
        it, :attr:`src.devices.BoardContext.key`); the face and a pixel
        matrix's pixel size are.
        """
        parts = [self.device_model or self.technology, self.charset, self.color, self.tile_gap]
        if self.width is not None and self.height is not None:
            parts.append(f"{self.width}x{self.height}")
        if self.font is not None:
            parts.append(self.font)
        return "|".join(str(part) for part in parts)

    def supports(self, feature: str) -> bool:
        """Whether this display can draw *feature* (one of :data:`FEATURES`).

        ``"solid_shapes"`` means same-coloured tiles join into one filled area
        (an LED board in the seamless tile style). ``"pixels"`` means a
        pixel matrix: it draws a page's pixel canvases (any pixel, any colour
        on an RGB panel), and :attr:`width` / :attr:`height` are its size. An
        unknown feature name is a programming error and raises ``ValueError``.
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
            "pixels": self.width is not None and self.height is not None,
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
            "led_matrix": "a full-colour LED pixel display" if self.color == "rgb" else "an LED pixel display",
            "screen": "a screen",
        }.get(self.technology, "a display board")
        lines = [f"THE DISPLAY: {kind}."]
        size = []
        if self.rows and self.cols:
            size.append(f"It shows {self.rows} rows of {self.cols} characters")
        if self.font is not None:
            face = "large" if self.font == "5x7" else "small"
            size.append(("in" if size else "Text is drawn in") + f" the {face} {self.font} text face")
        if size:
            lines.append(" ".join(size) + ". Keep every line within that width.")
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
        if self.supports("pixels"):
            lines.append(
                f"It is a {self.width} x {self.height} pixel matrix: a page can also hold pixel canvases "
                "(drawings over a block of character cells, in any "
                + ("colour" if self.color == "rgb" else "lit or unlit pixels")
                + "), and text under a canvas is hidden or flows around it."
            )
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
    model: Mapping[str, Any],
    charset: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    grid: tuple[int, int] | None = None,
) -> DisplayProfile:
    """One :class:`DisplayProfile` from a resolved (effective) device model,
    character set, the board's output config (for the LED tile style) and its
    content grid."""
    charset = charset or {}
    color = model.get("color")
    color_kind = color.get("kind") if isinstance(color, Mapping) else None
    # The tile style the device is actually drawn with: the board's choice
    # resolved against what its model allows (the preview uses the same).
    layout = led_layout_choice(model, config)
    geometry = model.get("geometry")
    pixel_size = None
    if isinstance(geometry, Mapping) and geometry.get("kind") == "pixels":
        pixel_size = (int(geometry["width"]), int(geometry["height"]))
    icons = charset.get("icons") or ()
    chars = charset.get("chars") or ()
    return DisplayProfile(
        technology=str(model.get("technology") or "unknown"),
        device_model=str(model.get("id")) if model.get("id") else None,
        charset=str(charset.get("id")) if charset.get("id") else None,
        color="rgb" if color_kind == "rgb" else ("mono" if color_kind == "mono" else "tiles"),
        mixed_case=bool(charset.get("mixedCase")),
        color_spans=bool(charset.get("colorSpans")),
        block_spans=bool(charset.get("blockSpans")),
        tiles=bool(charset.get("tiles", True)),
        icons=tuple(str(i) for i in icons if str(i) in BOARD_ICONS),
        chars="".join(str(c) for c in chars),
        tile_gap=layout.tile_gap if layout is not None else None,
        font=layout.font if layout is not None else None,
        rows=grid[0] if grid else None,
        cols=grid[1] if grid else None,
        width=pixel_size[0] if pixel_size else None,
        height=pixel_size[1] if pixel_size else None,
    )


def _grid(rows: Any, cols: Any) -> tuple[int, int] | None:
    if isinstance(rows, int) and isinstance(cols, int) and rows > 0 and cols > 0:
        return rows, cols
    return None


def _client_grid(plugin: Any) -> tuple[int, int] | None:
    try:
        grid = getattr(plugin, "board_geometry", None)
    except Exception:  # a hint, never an error
        return None
    return _grid(*grid) if isinstance(grid, tuple) and len(grid) == 2 else None


def display_profile_for_client(client: Any) -> DisplayProfile | None:
    """The :class:`DisplayProfile` of the board behind *client* (a board's
    output driver), or ``None`` when the driver does not describe its device
    (a test double, a legacy client).
    """
    model = _model_of(client)
    if model is None:
        return None
    plugin = getattr(client, "plugin", None)
    config = getattr(plugin, "config", None)
    return _profile(
        model, _charset_of(client, model), config if isinstance(config, Mapping) else None, _client_grid(plugin)
    )


def display_profile_for_board(board: Mapping[str, Any]) -> DisplayProfile | None:
    """The :class:`DisplayProfile` of a board's settings entry, resolved the
    way previews resolve it (:mod:`src.outputs.board_profile`); ``None`` when
    the board's device model is unknown (its output plugin is not installed).
    """
    model = board_device_model(board)
    if not isinstance(model, Mapping):
        return None
    config = board.get("output_config")
    return _profile(
        model,
        board_character_set(board),
        config if isinstance(config, Mapping) else None,
        _grid(board.get("grid_rows"), board.get("grid_cols")),
    )


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


def board_layers_json(board: Mapping[str, Any] | None, cells: Any) -> list[dict[str, Any]] | None:
    """What a board shows of a page's pixel canvases, as API JSON.

    ``None`` for a board that is not a pixel matrix (the response leaves the
    key out); otherwise the layers the frame *cells* carry
    (:class:`~src.outputs.cells.RichCells`), ``[]`` when it carries none.
    """
    if not isinstance(board, Mapping):
        return None
    try:
        profile = display_profile_for_board(board)
    except Exception:  # a hint for a read endpoint, never its failure
        return None
    if profile is None or not profile.supports("pixels"):
        return None
    from .cells import frame_layers

    return [layer.to_json() for layer in frame_layers(cells)]
