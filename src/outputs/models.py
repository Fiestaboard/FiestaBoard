"""Wire models of the outputs domain (``POST /outputs/{output_id}/boards``)."""

from __future__ import annotations

from typing import Any, Literal

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


# --- board settings actions and the outputs listing (plan D13) ----------------------------------


class SavedBoardActionRequest(BaseModel):
    """``POST /boards/{board_id}/actions/{action}``: run an action on a saved board."""

    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any] = Field(
        default_factory=dict, description="The action's input, checked against its declared input_schema."
    )
    output_config: dict[str, Any] | None = Field(
        default=None,
        description=(
            'Edited, unsaved board settings to run the action against; every "***" is restored from the stored '
            "board exactly as saving does. Left out: the stored settings."
        ),
    )


class DraftActionRequest(BaseModel):
    """``POST /outputs/{output_id}/actions/{action}``: run an action before a board exists."""

    model_config = ConfigDict(extra="forbid")

    output_config: dict[str, Any] = Field(
        default_factory=dict,
        description='The settings being entered. A draft has nothing stored, so "***" is refused.',
    )
    input: dict[str, Any] = Field(default_factory=dict, description="The action's input.")
    device_model: str | None = Field(
        default=None, description="Device model the board would be created as (default: the output's first)."
    )


class ActionResultField(BaseModel):
    """A value the settings form fills. A ``secret`` is a credential: never
    logged, and stored through the form's secret path."""

    value: Any
    secret: bool = False
    fills: str | None = Field(default=None, description="The settings field to fill; null = the result field's name.")


class ActionGeometry(BaseModel):
    """A detected board size: the ``POST /settings/board/{id}/detect-size``
    shape (``DetectBoardSizeResponse``), so applying it is unchanged. An output
    plugin's board reports ``device_type: "panel"``."""

    device_type: Literal["flagship", "note", "note_array", "panel"]
    rows: int
    cols: int
    notes_wide: int | None = None
    notes_tall: int | None = None
    matched_preset: str | None = None


class DiscoveredDevice(BaseModel):
    """A device a ``discover`` action found."""

    ip: str
    port: int
    hostname: str | None = None
    source: str | None = None
    label: str | None = None


class ActionResult(BaseModel):
    """Every action's answer: one closed envelope the settings form renders.

    ``status: "error"`` is the device's verdict (a refused key, nothing
    found), at 200 — what the server refused before contacting the device
    is a 4xx (API_CONVENTIONS.md, "Probe endpoints").
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error", "warning"]
    message: str
    guidance: list[str] = Field(default_factory=list, description="Plain-language next steps.")
    fields: dict[str, ActionResultField] | None = Field(default=None, description="Values to fill in the form.")
    geometry: ActionGeometry | None = None
    devices: list[DiscoveredDevice] | None = None


class OutputActionDescriptor(BaseModel):
    """One button of an output's board settings screen."""

    id: str
    label: str
    description: str = ""
    builtin: bool = Field(description="test_connection, discover, identify or detect_geometry: a core hook.")
    input_schema: dict[str, Any] | None = None
    result_fields: dict[str, dict[str, Any]] = Field(default_factory=dict)


class OutputDeviceModel(BaseModel):
    id: str
    label: str


class OutputCapabilitiesSummary(BaseModel):
    technology: str
    delivery: str
    animation: str
    native_transitions: list[str]
    charset: str | None = None


class OutputSummary(BaseModel):
    """An installed output: what "add a board" and the settings screen render from."""

    id: str
    name: str
    description: str
    icon: str | None
    builtin: bool = Field(description="Vestaboard and FiestaPanel: created through their own flows.")
    beta_gated: bool = Field(description="A third-party output plugin, usable only with the output plugins beta.")
    available: bool = Field(description="Whether a board can use it now (false: the beta is off).")
    output_api: int | None = Field(description="The contract major an output plugin targets; null for a built-in.")
    capabilities: OutputCapabilitiesSummary
    device_models: list[OutputDeviceModel]
    settings_schema: dict[str, Any] = Field(
        description="JSON Schema of output_config, with its ui:sections / ui:visible_when / ui:widget annotations."
    )
    actions: list[OutputActionDescriptor]


class AvailableOutput(BaseModel):
    """An output the user can pick, installed or not (``GET /outputs/available``)."""

    id: str
    name: str
    description: str
    icon: str | None
    source: Literal["installed", "seed", "registry"] = Field(
        description="installed: usable now; seed: bundled with this image (installs offline); "
        "registry: installs from its repository."
    )
    installed: bool
    builtin: bool = Field(description="Vestaboard and FiestaPanel: created through their own flows.")
    beta_gated: bool = Field(description="Usable only with the output plugins beta.")
    available: bool = Field(description="Whether it can be installed and used now (false: the beta is off).")
    needs_network: bool = Field(description="Installing it fetches its repository.")
    output_api: int | None = Field(
        description="The contract major it targets, where known before install; null for a built-in or a registry entry."
    )
