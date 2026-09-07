"""Request and response models for the ``/config`` endpoints.

Phase 2 §2: every route in a converted domain answers through a declared
``response_model`` and takes a Pydantic body, so the wire contract lives in
one reviewable place instead of in whichever dict a handler happened to build.

Two shapes here are deliberately *not* the conventional bare-resource body:

``BoardConfigResponse`` / ``BoardConfigUpdateResponse``
    ``GET|PUT /config/board`` is a deprecation shim (issue #1760) whose whole
    job is wire stability for callers that have not migrated to
    ``/settings/board``. Unwrapping its envelope would break the thing the
    shim exists to protect, so it keeps its legacy shape — now declared.

``BoardTestResponse`` / ``EnableLocalApiResponse``
    Probe endpoints whose declared job is to report an upstream verdict.
    "The board rejected this key" is the answer the caller asked for, at 200
    (#1887, Task 10a). Legitimate only because the shape is declared: an
    ad-hoc dict at 200 is indistinguishable from a success to a generic
    client.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, RootModel


class ConfigSummaryResponse(BaseModel):
    """``GET /config`` — the summary the dashboard header reads.

    Deliberately carries no credential, masked or otherwise; ``*_key_set``
    booleans report whether one is configured.
    """

    weather_provider: str
    weather_location: str
    timezone: str
    refresh_interval_seconds: int
    datetime_enabled: bool
    weather_enabled: bool
    guest_wifi_enabled: bool
    home_assistant_enabled: bool
    star_trek_quotes_enabled: bool
    air_fog_enabled: bool
    muni_enabled: bool
    surf_enabled: bool
    baywheels_enabled: bool
    traffic_enabled: bool
    stocks_enabled: bool
    board_api_mode: str
    board_host: str
    board_key_set: bool
    weather_key_set: bool
    transition_strategy: str | None = None
    transition_interval_ms: int | None = None
    transition_step_size: int | None = None


class FullConfigResponse(RootModel[dict[str, Any]]):
    """``GET /config/full`` — the whole masked ``config.json``.

    An open map on purpose, and the one route in this domain that cannot have
    a closed schema: the document grows a section per installed plugin, so a
    fixed model would silently *drop* every section it did not know about —
    strictly worse than declaring the shape honestly as "the config document".
    """


class LegacyBoardConfig(BaseModel):
    """The legacy ``config.json`` board block, as the shim still serves it.

    Sensitive fields read back as ``"***"`` when a value is stored and ``""``
    when it is not, so a blank credential stays distinguishable from a
    configured one.
    """

    api_mode: str
    local_api_key: str
    cloud_key: str
    note_array_token: str
    host: str
    transition_strategy: str | None = None
    transition_interval_ms: int | None = None
    transition_step_size: int | None = None


class BoardConfigResponse(BaseModel):
    """``GET /config/board`` — deprecated shim shape (issue #1760)."""

    config: LegacyBoardConfig
    api_modes: list[str]


class BoardConfigUpdate(BaseModel):
    """``PUT /config/board`` body — the five legacy connection fields.

    Every field is optional and the handler writes only the ones the caller
    actually sent (``exclude_unset``): the wizard saves a host without a key,
    and materialising the absent key as ``None`` would blank the stored one.

    Fields outside this set are ignored, matching the dict comprehension this
    model replaced — the deprecated shim is not a back door into board
    metadata.
    """

    api_mode: str | None = None
    local_api_key: str | None = None
    cloud_key: str | None = None
    note_array_token: str | None = None
    host: str | None = None


class BoardConfigUpdateResponse(BaseModel):
    """``PUT /config/board`` — deprecated shim shape (issue #1760)."""

    status: str
    config: LegacyBoardConfig


class BoardConfigResetResponse(BaseModel):
    """``DELETE /config/board`` — the wizard-reset acknowledgement."""

    status: str
    message: str


class ConfigValidationResponse(BaseModel):
    """``GET /config/validate`` — the setup wizard's gate.

    ``valid: false`` is a *verdict*, not a failure: the caller asked whether
    the install is configured and this is the answer, at 200.
    """

    valid: bool
    is_first_run: bool
    errors: list[str]
    missing_fields: list[str]


class BoardTestRequest(BaseModel):
    """``POST /config/board/test`` body."""

    api_mode: str = "local"
    local_api_key: str | None = None
    cloud_key: str | None = None
    host: str | None = None
    # Local API port (default 7000). Local-array tiles can sit on other ports.
    port: int | None = None


class BoardTestResponse(BaseModel):
    """Declared verdict of a board connection probe.

    ``POST /config/board/test`` is a *probe*: reporting "the board refused
    this key" is the answer the caller asked for, not a transport failure,
    so an upstream verdict stays HTTP 200 with ``success=False``. That is
    only legitimate because the shape is declared here — an ad-hoc dict at
    200 is indistinguishable from a success to any generic client (#1887).
    Preconditions the server rejects before probing (missing credential,
    malformed/unsafe host) are 4xx; unanticipated errors are 5xx.
    """

    success: bool
    message: str
    api_mode: str | None = None
    error: str | None = None
    troubleshooting: list[str] | None = None


class EnablementTokenRequest(BaseModel):
    """``POST /config/board/enable-local-api`` body."""

    host: str
    enablement_token: str


class EnableLocalApiResponse(BaseModel):
    """Declared verdict of a Local API enablement exchange.

    Same contract as :class:`BoardTestResponse` (see its docstring): the
    board's answer — including "that token is not valid" — is data at 200;
    preconditions are 4xx; unanticipated errors are 5xx.
    """

    success: bool
    message: str
    api_key: str | None = None
    error: str | None = None


class BoardScanRequest(BaseModel):
    """``POST /config/board/scan`` body. The handler clamps to [1, 15] s."""

    timeout: float | None = 4.0


class DiscoveredBoard(BaseModel):
    """One device the network sweep found."""

    ip: str
    port: int
    hostname: str
    source: str


class BoardScanResponse(BaseModel):
    """``POST /config/board/scan`` — what the sweep found."""

    boards: list[DiscoveredBoard]


class GeneralConfig(BaseModel):
    """``GET|PUT /config/general`` — the general settings block.

    ``extra="allow"`` because this is a stored document, not a computed view:
    an install upgraded from an older version can carry a key this build does
    not know, and a closed model would drop it from the response.
    """

    model_config = ConfigDict(extra="allow")

    timezone: str = "America/Los_Angeles"
    refresh_interval_seconds: int = 300
    output_target: str = "board"
    instance_name: str = ""
    time_format: str = "12h"
    date_format: str = "MM/DD/YYYY"
    welcome_message: str = ""


class GeneralConfigUpdate(BaseModel):
    """``PUT /config/general`` body — a partial update.

    Only the fields the caller sent are written (``exclude_unset``), matching
    the ``if "<key>" in request`` chain this model replaced.

    ``refresh_interval_seconds`` is typed. The endpoint used to take a bare
    ``dict`` and hand it straight to the store, so
    ``{"refresh_interval_seconds": "soon"}`` persisted and then broke every
    consumer that did arithmetic on it; it is now a 422.
    """

    timezone: str | None = None
    refresh_interval_seconds: int | None = None
    output_target: str | None = None
    instance_name: str | None = None
    time_format: str | None = None
    date_format: str | None = None
    welcome_message: str | None = None
