"""Request and response models for the ``/settings`` router.

Written by the Phase 2 conventions pass (Task 8). Every ``/settings`` route
declares one of these as its ``response_model``, and every route with a body
takes one instead of a bare ``dict`` — the two rules the conventions ratchet
(``tests/test_api_conventions_ratchet.py``) enforces.

Two conventions carry real weight here and are easy to undo by accident:

**``StrictBool``, never ``bool``.** Pydantic's default (lax) mode coerces
``"yes"``, ``1``, ``"on"`` and ``"true"`` to ``True``. Three endpoints used to
hand-roll ``isinstance(x, bool)`` precisely to refuse those; replacing that
check with a plain ``bool`` field would silently *loosen* the contract while
looking like a conventions win. ``tests/test_settings_contract.py`` pins each
of them with a truthy-string case.

**Partial updates use ``exclude_unset``.** Several setters distinguish "field
omitted" from "field set to null" — ``PUT /settings/transitions`` clears a
strategy with an explicit ``null`` and leaves it alone when the key is absent.
Those handlers read ``request.model_dump(exclude_unset=True)`` rather than the
full dump, so an unset optional field never overwrites stored state with
``None``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from src.config import SilenceMode
from src.devices import DeviceType
from src.settings.service import VALID_OUTPUT_TARGETS

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------


class MqttSettingsResponse(BaseModel):
    """MQTT integration settings, password masked."""

    enabled: bool
    broker_host: str
    broker_port: int
    username: str
    password: str
    external_url: str


class MqttSettingsUpdate(BaseModel):
    """Partial MQTT update: omitted fields keep their stored value."""

    enabled: StrictBool | None = None
    broker_host: str | None = None
    broker_port: int | None = None
    username: str | None = None
    password: str | None = None
    external_url: str | None = None


# ---------------------------------------------------------------------------
# AI providers
# ---------------------------------------------------------------------------


class AiProvidersResponse(BaseModel):
    """AI provider configuration with every ``api_key`` masked."""

    enabled: bool
    providers: list[dict[str, Any]]
    default_provider_id: str | None = None


class AiProvidersUpdate(BaseModel):
    """Partial AI-provider update.

    ``providers`` entries stay untyped on purpose: a provider is a BYO-LLM
    endpoint description whose accepted fields are the provider's, not ours,
    and the config manager owns their validation. This is a *response*-shaped
    passthrough, not a bare ``dict`` body parameter — the model still pins
    which top-level keys exist.
    """

    enabled: StrictBool | None = None
    providers: list[dict[str, Any]] | None = None
    default_provider_id: str | None = None


class AiTestRequest(BaseModel):
    """Smoke-test one provider, optionally an unsaved draft from the UI."""

    provider_id: str | None = None
    model: str | None = None
    provider: dict[str, Any] | None = None


class AiTestResponse(BaseModel):
    """Verdict of a provider smoke test.

    ``ok`` false at HTTP 200 is the documented probe exception
    (API_CONVENTIONS.md, "Probe endpoints"): the caller asked for a verdict
    about a third-party endpoint it named, "your key was rejected" is the
    payload rather than a transport failure, and the verdict arrives as this
    declared model rather than an ad-hoc dict. Anything the server rejects
    *before* probing (no providers configured, unknown provider id) is a real
    4xx.
    """

    ok: bool
    message: str
    model_used: str | None = None


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


class TransitionSettings(BaseModel):
    """Board transition animation settings."""

    strategy: str | None = None
    step_interval_ms: int | None = None
    step_size: int | None = None


class TransitionSettingsResponse(TransitionSettings):
    """Transition settings plus the strategies this install can offer."""

    available_strategies: list[str]


class TransitionSettingsUpdate(BaseModel):
    """Partial transition update.

    An explicit ``null`` clears a field; an omitted key leaves it alone. The
    handler tells the two apart with ``exclude_unset``.
    """

    strategy: str | None = None
    step_interval_ms: int | None = None
    step_size: int | None = None


# ---------------------------------------------------------------------------
# Output target
# ---------------------------------------------------------------------------


class OutputSettings(BaseModel):
    """Where rendered content is sent."""

    target: str


class OutputSettingsResponse(OutputSettings):
    """Output target plus the targets this install can offer."""

    effective_target: str
    available_targets: list[str]


class OutputSettingsUpdate(BaseModel):
    """Set the output target.

    The vocabulary is published (derived from ``VALID_OUTPUT_TARGETS``) but
    the field stays ``str``: ``SettingsService.set_output_target`` already
    refuses an unknown target, and the handler turns that into a 400 whose
    detail names the valid set. Moving the verdict to Pydantic would trade
    that message for a generic 422 and change a recorded status code for no
    gain — the defect here was the missing *documentation*, not a missing
    check.
    """

    target: str = Field(json_schema_extra={"enum": VALID_OUTPUT_TARGETS})


# ---------------------------------------------------------------------------
# Active page
# ---------------------------------------------------------------------------


class ActivePageResponse(BaseModel):
    """The active page selection, with the collection member it resolves to."""

    page_id: str | None = None
    resolved_page_id: str | None = None
    resolved_next_check_seconds: int | None = None
    board_id: str | None = None


class SetActivePageRequest(BaseModel):
    """Select the active page (or ``null`` to clear it)."""

    page_id: str | None = None
    board_id: str | None = None


class SetActivePageResponse(BaseModel):
    """Result of selecting an active page.

    The selection is persisted whether or not the immediate send succeeded;
    ``sent_to_board`` and ``error`` report the send half. ``warnings`` is
    always present — it used to be omitted when empty, which made "no
    warnings" and "this build does not report warnings" indistinguishable.
    """

    page_id: str | None = None
    sent_to_board: bool
    paused: bool
    board_id: str | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Temporary override
# ---------------------------------------------------------------------------


class TemporaryOverrideResponse(BaseModel):
    """The active temporary override, or every field nulled when there is none."""

    active: bool
    page_id: str | None = None
    expires_at: str | None = None
    remaining_seconds: float | None = None
    revert_mode: str | None = None
    revert_page_id: str | None = None
    template: list[str] | None = None
    line_metadata: list[dict[str, Any]] | None = None
    device_type: str | None = None
    notes_wide: int | None = None
    notes_tall: int | None = None


class TemporaryOverrideRequest(BaseModel):
    """Activate an override from a saved page or from inline content."""

    page_id: str | None = None
    template: list[Any] | None = None
    line_metadata: list[Any] | None = None
    device_type: DeviceType | None = None
    notes_wide: Any | None = None
    notes_tall: Any | None = None
    duration_minutes: Any | None = None
    revert_mode: str = "schedule"
    revert_page_id: str | None = None


class ClearTemporaryOverrideResponse(BaseModel):
    """What the cancelled override was going to revert to."""

    revert_mode: str | None = None


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


class PollingSettings(BaseModel):
    """How often FiestaBoard polls its own state and the board's."""

    interval_seconds: int
    board_read_interval_local: int
    board_read_interval_cloud: int


class PollingSettingsResponse(PollingSettings):
    """Polling settings plus whether the change needs a container restart."""

    requires_restart: bool


class PollingSettingsUpdate(BaseModel):
    """Partial polling update: only the intervals present are changed."""

    interval_seconds: int | None = None
    board_read_interval_local: int | None = None
    board_read_interval_cloud: int | None = None


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------


class BoardSettingsResponse(BaseModel):
    """Board settings: the install's board colour, its boards, its device types.

    Board entries stay ``dict`` because a board carries per-tile credential
    sub-objects and mode-dependent fields; typing them is
    ``src/devices.py::BoardInstance``'s job and a separate slice. This is a
    response body, not a request body — the ``typed_body`` rule does not
    apply, and the ratchet checks that distinction.
    """

    board_type: str | None = None
    boards: list[dict[str, Any]]
    devices: list[str]


class BoardSettingsUpdate(BaseModel):
    """Update the board colour, the device list, or the whole boards array.

    Exactly one is acted on per call, in the order ``devices``, ``boards``,
    ``board_type`` — preserved from the pre-conversion handler.
    """

    board_type: str | None = None
    devices: list[str] | None = None
    boards: list[dict[str, Any]] | None = None


class AddBoardRequest(BaseModel):
    """Add a board instance. Only ``device_type`` is required.

    ``extra="allow"`` keeps the pre-conversion behaviour of forwarding any
    board field the caller supplies (``tiles``, ``code62_glyph``, future
    fields) to ``BoardInstance.from_dict``, which owns the real validation.
    """

    model_config = ConfigDict(extra="allow")

    #: ``DeviceType``, not ``str``: BoardInstance.__post_init__ rewrites an
    #: unknown device_type to "flagship", so ``{"device_type": "bogus"}``
    #: created a flagship board and answered 201. The vocabulary is now in
    #: the schema and the coercion is unreachable from here.
    device_type: DeviceType
    name: str | None = None


class BoardPauseRequest(BaseModel):
    """Pause or resume one board.

    ``StrictBool``: ``{"paused": "yes"}`` must be a 422, not a paused board.
    """

    paused: StrictBool


class BoardPauseResponse(BaseModel):
    """The board's new pause state, plus the board settings it now lives in."""

    board_id: str
    paused: bool
    board_settings: BoardSettingsResponse


class DetectBoardSizeResponse(BaseModel):
    """A board's device type and grid, classified from its live layout."""

    device_type: DeviceType
    rows: int
    cols: int
    notes_wide: int | None = None
    notes_tall: int | None = None
    matched_preset: str | None = None


class BoardIdentifyRequest(BaseModel):
    """Request body for the local note-array identify flash.

    ``target: "tile"`` identifies one slot (``row``/``col`` required unless
    the credential override is supplied); ``target: "all"`` flashes every
    configured tile at once. The optional ``host``/``port``/``local_api_key``
    override lets the assign dialog identify a board BEFORE its tile is
    saved — in that case ``row``/``col`` name the slot being assigned.
    """

    target: str = "tile"
    row: int | None = None
    col: int | None = None
    host: str | None = None
    port: int | None = None
    local_api_key: str | None = None


class BoardIdentifyTileResult(BaseModel):
    """Whether one tile accepted its identify pattern."""

    row: int
    col: int
    success: bool


class BoardIdentifyResponse(BaseModel):
    """Per-tile outcome of an identify flash."""

    board_id: str
    results: list[BoardIdentifyTileResult]


# ---------------------------------------------------------------------------
# Display / location
# ---------------------------------------------------------------------------


class DisplaySettingsResponse(BaseModel):
    """Web-UI display preferences (never the physical board's pacing)."""

    reduce_motion: bool
    board_animations: str
    site_animations: str
    board_flap_speed: str | int


class DisplaySettingsUpdate(BaseModel):
    """Partial display update: only the preferences present are changed."""

    reduce_motion: StrictBool | None = None
    board_animations: str | None = None
    site_animations: str | None = None
    board_flap_speed: str | int | None = None


class LocationSettingsResponse(BaseModel):
    """Coordinates used for sunrise/sunset schedules."""

    latitude: float | None = None
    longitude: float | None = None


class LocationSettingsUpdate(BaseModel):
    """Partial location update: an explicit ``null`` clears a coordinate."""

    latitude: float | None = None
    longitude: float | None = None


class SunTimesResponse(BaseModel):
    """Sunrise/sunset for one date, or nulls when they cannot be computed."""

    sunrise: str | None = None
    sunset: str | None = None
    location_configured: bool


class SunTimesForDay(BaseModel):
    """Sunrise and sunset as HH:MM strings."""

    sunrise: str
    sunset: str


class SunTimesWeekResponse(BaseModel):
    """Sunrise/sunset for each day of a week, keyed by ISO date."""

    location_configured: bool
    dates: dict[str, SunTimesForDay]


# ---------------------------------------------------------------------------
# Beta
# ---------------------------------------------------------------------------


class BetaSettings(BaseModel):
    """Opt-in beta feature flags."""

    https_enabled: bool
    transition_plugins_enabled: bool


class BetaHttpsStatus(BaseModel):
    """Runtime status of the HTTPS beta feature."""

    cert_present: bool
    cert_path: str
    key_path: str
    updater_available: bool


class BetaSettingsResponse(BaseModel):
    """Beta flags plus the certificate/sidecar status behind them."""

    settings: BetaSettings
    https: BetaHttpsStatus


class BetaSettingsUpdateResponse(BetaSettingsResponse):
    """Beta flags after a write, plus whether a restart is needed."""

    restart_required: bool


class BetaSettingsUpdate(BaseModel):
    """Partial beta update: only the flags present are changed."""

    https_enabled: StrictBool | None = None
    transition_plugins_enabled: StrictBool | None = None


# ---------------------------------------------------------------------------
# Plugin settings
# ---------------------------------------------------------------------------


class PluginSettingsResponse(BaseModel):
    """Plugin-system settings."""

    auto_update: bool


class PluginSettingsUpdate(BaseModel):
    """Partial plugin-settings update.

    ``StrictBool``: the pre-conversion handler passed the raw body through to
    ``bool(...)``, so ``{"auto_update": "yes"}`` silently enabled background
    plugin updates.
    """

    auto_update: StrictBool | None = None


# ---------------------------------------------------------------------------
# Silence schedule
# ---------------------------------------------------------------------------


class SilenceScheduleRequest(BaseModel):
    """Update the silence ("snooze") window, install-wide or for one board."""

    enabled: bool
    start_time: str
    end_time: str
    # An unknown mode used to be coerced to "freeze" and answered 200, so a
    # client asking for "indicater" got a frozen board and no signal.
    mode: SilenceMode | None = None  # omitted → "freeze"
    page_id: str | None = None  # Page id to display when mode == "page"
    indicator_text: str | None = None  # Custom text to display when mode == "indicator"
    indicator_position: str | None = None  # Position: center, top-left, top-right, bottom-left, bottom-right
    # Board to target (issue #1788). Omitted → the install-wide schedule.
    # Deliberately in the BODY, not the URL, so the endpoint path is unchanged.
    board_id: str | None = None


class SilenceScheduleResponse(BaseModel):
    """The resolved silence configuration and the layer it was written to."""

    config: dict[str, Any]
    board_id: str | None = None


# ---------------------------------------------------------------------------
# HDMI kiosk
# ---------------------------------------------------------------------------


class HdmiKioskStatusResponse(BaseModel):
    """FiestaPi HDMI kiosk status.

    ``enabled`` is always present — ``null`` where the platform cannot report
    one (no sidecar, not a FiestaPi) rather than absent, so a client can tell
    "off" from "unknown" without inspecting which keys arrived.
    """

    model_config = ConfigDict(extra="allow")

    supported: bool
    status: str
    enabled: bool | None = None


class HdmiKioskRequest(BaseModel):
    """Enable or disable the HDMI kiosk.

    ``StrictBool``: ``{"enabled": "yes"}`` must not install a kiosk.
    """

    enabled: StrictBool


class HdmiKioskActionResponse(BaseModel):
    """The sidecar's answer to an enable/disable request.

    ``extra="allow"`` because the sidecar owns this payload and adds fields
    on its own release cadence; ``status`` is the only key FiestaBoard
    guarantees.
    """

    model_config = ConfigDict(extra="allow")

    status: str
    action: str | None = None


# ---------------------------------------------------------------------------
# GET /settings/all
# ---------------------------------------------------------------------------


class ServiceStatus(BaseModel):
    """Whether the display service is running."""

    running: bool


class SilenceScheduleBlock(BaseModel):
    """The silence-schedule feature block as ``/settings/all`` reports it."""

    config: dict[str, Any]


class ScheduleBehaviourBlock(BaseModel):
    """Global schedule behaviour, as served inside ``/settings/all``.

    Mirrors ``ScheduleBehaviorResponse`` from the schedules domain; declared
    here so ``AllSettingsResponse`` stays fully typed without importing a
    router-owned model across domains.
    """

    defer_on_reenable: bool = False


class AllSettingsResponse(BaseModel):
    """Everything the settings page loads, in one request.

    ``general`` stays a ``dict``: it is the config manager's block, owned by
    the (unconverted) ``/config`` domain, and typing it here would fork the
    definition. It becomes a model when that domain converts.
    """

    general: dict[str, Any]
    silence_schedule: SilenceScheduleBlock
    polling: PollingSettings
    transitions: TransitionSettingsResponse
    output: OutputSettings
    board: BoardSettingsResponse
    mqtt: MqttSettingsResponse
    display: DisplaySettingsResponse
    location: LocationSettingsResponse
    beta: BetaSettings
    plugins: PluginSettingsResponse
    schedule: ScheduleBehaviourBlock
    status: ServiceStatus


# ---------------------------------------------------------------------------
# Shared ``responses=`` declarations
# ---------------------------------------------------------------------------
#
# The conventions ratchet requires every route to declare the 4xx it can
# actually answer. These are the shared descriptions so a reader sees the same
# wording for the same failure across the domain.
#
# There is deliberately no ``ERROR_422``. There used to be — seven routes
# declared ``{422: {"description": "Validation error"}}``, which is worse
# than declaring nothing: a hand-written 422 entry *replaces* the
# ``HTTPValidationError`` body FastAPI publishes automatically, so the schema
# announced a 422 with an empty body and a consumer learned nothing about it.
# Validation errors are FastAPI's own contract (API_CONVENTIONS.md, "Typed
# request models"); let it declare them.

ERROR_400 = {400: {"description": "Invalid request"}}
ERROR_404 = {404: {"description": "Not found"}}
ERROR_409 = {409: {"description": "Conflict"}}
ERROR_500 = {500: {"description": "Server error"}}
ERROR_502 = {502: {"description": "Upstream (board or sidecar) error"}}
