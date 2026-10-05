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
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from src.fiestaui import builtin_device_models, fiestapanel_device_models
from src.led.charsets import BUILTIN_CHARACTER_SETS, materialize_character_set

from .registry import FIESTAPANEL, VESTABOARD, output_registry, resolve_output_id


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
    return BoardProfile(ids[index], _charset_id(manifest.model(index).get("charset")))


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
    if model is None or model.get("id") in builtin_device_models():
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


def board_device_model(board: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The FiestaUI DeviceModel an output-plugin board resolves to (see
    :func:`board_profile`), as the document; ``None`` for a built-in output
    or a plugin that is not installed."""
    output_id = resolve_output_id(board)
    if output_id in (VESTABOARD, FIESTAPANEL):
        return None
    definition = output_registry().get(output_id)
    manifest = definition.output_manifest if definition is not None else None
    if manifest is None or not manifest.device_models:
        return None
    ids = manifest.device_model_ids
    stored = board.get("device_model")
    return manifest.model(ids.index(stored) if stored in ids else 0)


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
