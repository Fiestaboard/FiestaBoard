"""Wire models of the outputs domain (``POST /outputs/{output_id}/boards``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.devices import MAX_BOARD_NAME_LENGTH


class OutputBoardGeometry(BaseModel):
    """The size of a board whose device model is sized per board.

    ``rows`` and ``cols`` for a ``panel`` model; ``notes_wide`` and
    ``notes_tall`` for a ``note_array`` model. Refused for a model with a
    fixed size (``cells``, ``pixels``), whose grid comes from the model.
    """

    model_config = ConfigDict(extra="forbid")

    rows: StrictInt | None = Field(default=None, ge=1)
    cols: StrictInt | None = Field(default=None, ge=1)
    notes_wide: StrictInt | None = Field(default=None, ge=1)
    notes_tall: StrictInt | None = Field(default=None, ge=1)


class OutputBoardCreate(BaseModel):
    """A new board driven by an output plugin."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        max_length=MAX_BOARD_NAME_LENGTH,
        description='Display name; "My Board", "My Board 2"... when left out.',
    )
    device_model: str = Field(
        min_length=1, description="One of the device model ids the output plugin declares in its manifest."
    )
    output_config: dict[str, Any] = Field(
        default_factory=dict,
        description="The board's settings, validated against the plugin's output.settings_schema.",
    )
    geometry: OutputBoardGeometry | None = Field(
        default=None,
        description="Only for a device model sized per board (panel: rows and cols; note_array: notes).",
    )


class OutputBoardResponse(BaseModel):
    """The board that was created, as the API shows it (secrets masked)."""

    id: str
    name: str
    output: str = Field(description="The output plugin that drives the board.")
    device_model: str = Field(description="The FiestaUI device model the board was created as.")
    charset: str | None = Field(description="The character set the board draws with (a FiestaUI id).")
    device_type: str = Field(description='Always "panel": a board with its own rows x cols content grid.')
    rows: int = Field(description="Content grid height in characters.")
    cols: int = Field(description="Content grid width in characters.")
    output_config: dict[str, Any] = Field(description='The board\'s settings, every secret shown as "***".')
