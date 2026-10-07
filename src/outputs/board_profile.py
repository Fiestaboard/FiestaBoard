"""What a board is drawn as: its FiestaUI device model and character set.

Board responses (``GET /settings/board``, ``/v1/boards``) report, beside the
board's ``output``, the **device model** id it resolves to and the
**character set** id it draws with (plan D15/D17), so a client can pick the
right preview and offer only drawable glyphs. Both are derived at read time,
never stored for a legacy board:

- **Vestaboard** — the built-in FiestaUI model whose ``legacy.deviceType`` is
  the board's ``device_type`` (``vestaboard_flagship``, ``vestaboard_note``,
  ``vestaboard_note_array``). A Flagship's character set follows its code-62
  flap (the model's ``charsetByCode62``: degree → ``vestaboard_v1``, heart →
  ``vestaboard_v2``); Note hardware only ever carried the heart.
- **FiestaPanel** — the model of its panel's ``render_style``
  (``fiestapanel_split_flap`` / ``fiestapanel_led_matrix``, FiestaBoard's own
  models from FiestaUI's ``plugin-models.json``; ``split_flap`` when no panel
  claims the board). A split-flap panel's character set follows its code-62
  flap exactly as a Flagship's does (degree → ``vestaboard_v1``, heart →
  ``vestaboard_v2``); an LED one draws with its model's (``led_5x7``).
- **An output plugin** — the model the board was created as, when the plugin
  still declares it, else the plugin's first (default) model; the character
  set the plugin declares, else that model's. When the plugin is not
  installed, the stored model id and no character set.

**Text size.** An LED board measured in pixels whose model offers a choice of
face (``layoutOptions.font``: Large ``"5x7"`` / Small ``"3x5"``) draws in the
face :func:`board_font` resolves, and is the model *with that face*
(:func:`~src.led.matrix.model_with_led_font`): its character set, grid,
display profile and output-plugin instance all follow it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, NamedTuple

from src.fiestaui import builtin_device_models, fiestapanel_device_models
from src.led.charsets import BUILTIN_CHARACTER_SETS, materialize_character_set
from src.led.matrix import LedLayoutChoice, layout_policy_for_model, led_layout_options_for_model, model_with_led_font

from .registry import FIESTAPANEL, VESTABOARD, output_registry, resolve_output_id

logger = logging.getLogger(__name__)

#: The ``output_config`` key an LED board's face (text size) is stored under:
#: ``"5x7"`` (Large) or ``"3x5"`` (Small), one the board's model offers.
FONT_CONFIG_KEY = "font"

#: (board id, value) pairs already warned about, so a stale stored face
#: logs once, not on every render.
_warned_fonts: set[tuple[Any, Any]] = set()


class BoardProfile(NamedTuple):
    device_model: str | None
    charset: str | None


def _charset_id(charset: Any) -> str | None:
    if isinstance(charset, str):
        return charset
    if isinstance(charset, Mapping) and isinstance(charset.get("id"), str):
        return charset["id"]
    return None


def _vestaboard(board: Mapping[str, Any]) -> BoardProfile:
    device_type = board.get("device_type") or "flagship"
    for model_id, model in builtin_device_models().items():
        legacy = model.get("legacy") or {}
        if model.get("technology") != "split_flap" or legacy.get("deviceType") != device_type:
            continue
        by_code62 = model.get("charsetByCode62")
        if isinstance(by_code62, Mapping):
            glyph = board.get("code62_glyph") if device_type == "flagship" else "heart"
            return BoardProfile(model_id, _charset_id(by_code62.get(glyph) or by_code62.get("degree")))
        return BoardProfile(model_id, _charset_id(model.get("charset")))
    return BoardProfile(None, None)


def _plugin(board: Mapping[str, Any], output_id: str) -> BoardProfile:
    stored = board.get("device_model") if isinstance(board.get("device_model"), str) else None
    definition = output_registry().get(output_id)
    manifest = definition.output_manifest if definition is not None else None
    if manifest is None:
        return BoardProfile(stored, None)
    ids = manifest.device_model_ids
    index = ids.index(stored) if stored in ids else 0
    if manifest.character_set is not None:
        return BoardProfile(ids[index], manifest.character_set["id"])
    model = board_device_model(board)
    return BoardProfile(ids[index], _charset_id(model.get("charset")) if model is not None else None)


def _panel_render_style(board: Mapping[str, Any]) -> str:
    """The render style of the panel whose virtual board *board* is.

    ``split_flap`` -- the only look a panel had before the setting existed --
    when no panel claims the board or the panel store cannot be read: a board
    response never fails over a preview hint.
    """
    board_id = board.get("id")
    if not isinstance(board_id, str):
        return "split_flap"
    try:
        from src.panels.service import get_panel_service

        panel = get_panel_service().get_panel_by_board_id(board_id)
    except Exception:  # a preview hint, never an error
        return "split_flap"
    return panel.render_style if panel is not None else "split_flap"


def _fiestapanel(board: Mapping[str, Any]) -> BoardProfile:
    model = fiestapanel_device_models()[_panel_render_style(board)]
    if model.get("technology") == "split_flap":
        # The flaps a panel draws carry the board's code-62 glyph, as a
        # Flagship's do (BoardInstance.effective_code62_glyph).
        from src.devices import BoardInstance

        glyph = BoardInstance.from_dict(dict(board)).effective_code62_glyph
        return BoardProfile(model["id"], "vestaboard_v2" if glyph == "heart" else "vestaboard_v1")
    return BoardProfile(model["id"], _charset_id(model.get("charset")))


def board_profile(board: Mapping[str, Any]) -> BoardProfile:
    """The device model id and character set id *board* resolves to."""
    output_id = resolve_output_id(board)
    if output_id == VESTABOARD:
        return _vestaboard(board)
    if output_id == FIESTAPANEL:
        return _fiestapanel(board)
    return _plugin(board, output_id)


def board_model_spec(board: Mapping[str, Any]) -> dict | None:
    """The device model document for a board whose model FiestaUI does not
    build in -- a FiestaPanel's, or an output plugin's own -- so a client can
    render it (``DisplayPreview`` resolves a built-in by id, anything else
    only from the document). ``None`` for a built-in model or an unknown one.
    """
    output_id = resolve_output_id(board)
    if output_id == VESTABOARD:
        return None
    if output_id == FIESTAPANEL:
        return dict(fiestapanel_device_models()[_panel_render_style(board)])
    model = board_device_model(board)
    if model is None:
        return None
    # A built-in model is sent only when the board draws it differently --
    # in the other face (text size), or as the output's own copy of it --
    # so a preview never draws the built-in's 3x5 for a 5x7 board.
    builtin = builtin_device_models().get(model.get("id"))
    if builtin is not None and dict(builtin) == dict(model):
        return None
    return dict(model)


def model_character_set(model: Mapping[str, Any]) -> dict | None:
    """A device model's own character set, whole: a built-in id looked up,
    an inline set materialised; ``None`` when it names none or an unknown id."""
    charset = model.get("charset")
    if isinstance(charset, str):
        return dict(BUILTIN_CHARACTER_SETS[charset]) if charset in BUILTIN_CHARACTER_SETS else None
    if isinstance(charset, Mapping):
        return materialize_character_set(dict(charset))
    return None


def offers_font_choice(model: Mapping[str, Any] | None) -> bool:
    """Whether *model* is an LED board measured in pixels, the only kind whose
    face sizes its grid (and so the only kind a text size applies to)."""
    if not isinstance(model, Mapping) or model.get("technology") != "led_matrix":
        return False
    geometry = model.get("geometry")
    return isinstance(geometry, Mapping) and geometry.get("kind") == "pixels"


def _face_grid(model: Mapping[str, Any], font: str) -> tuple[int, int] | None:
    from .geometry import GeometryError, model_cell_grid

    try:
        return model_cell_grid(model_with_led_font(model, font))
    except (GeometryError, KeyError, ValueError):
        return None


def board_font(board: Mapping[str, Any], model: Mapping[str, Any] | None) -> str | None:
    """The face (``"5x7"`` / ``"3x5"``) a board on *model* draws in; ``None``
    for a model that is not an LED board measured in pixels.

    1. ``output_config.font`` when the model offers it;
    2. a board with no ``font`` stored (saved before the choice existed): the
       offered face whose grid is the board's stored ``grid_rows`` x
       ``grid_cols`` -- an existing 10 x 16 Pixoo stays 3x5, and nothing is
       written back;
    3. else the model's own ``font``. A stored value the model does not offer
       lands here too, with a warning (once per board and value).

    *model* is the model the board was created as, as its output declares it
    (not the effective one :func:`board_device_model` returns).
    """
    if not offers_font_choice(model):
        return None
    assert model is not None
    allowed = layout_policy_for_model(model)["font"]["allowed"]
    config = board.get("output_config")
    requested = config.get(FONT_CONFIG_KEY) if isinstance(config, Mapping) else None
    own = led_layout_options_for_model(model).font
    if requested is not None:
        if isinstance(requested, str) and requested in allowed:
            return requested
        key = (board.get("id"), repr(requested))
        if key not in _warned_fonts:
            _warned_fonts.add(key)
            logger.warning(
                # Nothing read from the board is logged: its record (output_config) can hold secrets.
                "A %s board's text size is not one the model offers (%s); drawing in %s",
                model.get("id"),
                ", ".join(allowed),
                own,
            )
        return own
    stored = (board.get("grid_rows"), board.get("grid_cols"))
    for font in allowed:
        if _face_grid(model, font) == stored:
            return font
    return own


def board_device_model(board: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The FiestaUI DeviceModel an output-plugin board resolves to (see
    :func:`board_profile`), as the document; ``None`` for a built-in output
    or a plugin that is not installed.

    An LED board drawn in a face other than its model's own is that model
    with the face (:func:`board_font`) and its character set swapped in. An
    output that declares its own character set fixes the face (plan D17).
    """
    output_id = resolve_output_id(board)
    if output_id in (VESTABOARD, FIESTAPANEL):
        return None
    definition = output_registry().get(output_id)
    manifest = definition.output_manifest if definition is not None else None
    if manifest is None or not manifest.device_models:
        return None
    ids = manifest.device_model_ids
    stored = board.get("device_model")
    model = manifest.model(ids.index(stored) if stored in ids else 0)
    if manifest.character_set is not None:
        return model
    font = board_font(board, model)
    return model_with_led_font(model, font) if font is not None else model


def board_character_set(board: Mapping[str, Any]) -> dict | None:
    """The whole (materialised) character set *board* draws with, or ``None``.

    Resolved exactly as :func:`board_profile` resolves its id: a Vestaboard's
    built-in set by its flap; a FiestaPanel's by its render style (and, for
    split-flap, its flap); an output plugin's declared set, else its
    board's model's (a built-in id, or an inline set made whole). ``None``
    for a plugin that is not installed — unknown is never guessed.
    """
    output_id = resolve_output_id(board)
    if output_id in (VESTABOARD, FIESTAPANEL):
        charset_id = (_vestaboard(board) if output_id == VESTABOARD else _fiestapanel(board)).charset
        return dict(BUILTIN_CHARACTER_SETS[charset_id]) if charset_id in BUILTIN_CHARACTER_SETS else None
    definition = output_registry().get(output_id)
    manifest = definition.output_manifest if definition is not None else None
    if manifest is None:
        return None
    if manifest.character_set is not None:
        return manifest.character_set
    model = board_device_model(board)
    return model_character_set(model) if model is not None else None


#: The ``output_config`` keys an LED board's byte-changing layout choices are
#: stored under (plan D23), the same for every LED output, with the values
#: FiestaUI's ``LedLayoutOptions`` takes (``tile_gap``: ``"gap"`` | ``"fill"``;
#: ``block_padding``: ``0`` | ``1``). An output offers them by declaring these
#: properties in its ``settings_schema``; a board that never set one draws
#: with its model's default.
LED_LAYOUT_CONFIG_KEYS = ("tile_gap", "block_padding")


def led_layout_choice(model: Mapping[str, Any] | None, config: Mapping[str, Any] | None) -> LedLayoutChoice | None:
    """The LED layout options a board on *model* with *config* draws with.

    Each choice the model's ``layoutOptions`` allows, else the model's
    default (the reason in ``ignored``); ``None`` for a model that is not an
    LED matrix (a split-flap board has no LED layout) or no model at all.
    """
    if not isinstance(model, Mapping) or model.get("technology") != "led_matrix":
        return None
    config = config if isinstance(config, Mapping) else {}
    # The face is not re-read from *config*: the model in hand is already the
    # board's effective one (:func:`board_device_model` resolved the face into
    # it), so its own ``font`` is the face it draws in.
    return led_layout_options_for_model(
        model, tile_gap=config.get("tile_gap"), block_padding=config.get("block_padding")
    )


def board_led_layout(board: Mapping[str, Any]) -> dict[str, Any] | None:
    """What an LED board draws with, for a preview: ``{"tile_gap", "block_padding", "font"}``.

    The board's ``output_config`` choices resolved against its device model
    (:func:`led_layout_choice`), so a preview draws the bytes the device is
    sent. ``None`` for a board that is not an LED matrix, or whose model is
    unknown (an output plugin that is not installed).
    """
    output_id = resolve_output_id(board)
    if output_id == VESTABOARD:
        return None
    config: Mapping[str, Any] | None = None
    if output_id == FIESTAPANEL:
        # A panel offers no LED layout settings: its model's defaults.
        model: Mapping[str, Any] | None = fiestapanel_device_models()[_panel_render_style(board)]
    else:
        model = board_device_model(board)
        raw = board.get("output_config")
        config = raw if isinstance(raw, Mapping) else None
    choice = led_layout_choice(model, config)
    if choice is None:
        return None
    return {"tile_gap": choice.tile_gap, "block_padding": choice.block_padding, "font": choice.font}
