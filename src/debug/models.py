"""Response and request models for the debug / diagnostics / logs endpoints.

Phase 2 Task 8. Before this pass every one of these routes returned an
untyped dict, most of them wrapped in a ``{"status": "success", ...}``
envelope that told a caller nothing the HTTP status code did not already say.
The models here are the contract the TypeScript client in
``web/src/lib/api/system.ts`` is generated against by eye and checked against
by ``/check-types``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt

# ---------------------------------------------------------------------------
# Board actions
# ---------------------------------------------------------------------------


class BoardFillRequest(BaseModel):
    """Body of ``POST /debug/fill``.

    ``StrictInt`` rather than ``int`` on purpose: this replaces a hand-rolled
    ``isinstance(character_code, int)`` check, and Pydantic's lax mode would
    coerce ``"65"`` — and, because ``bool`` is a subclass of ``int``, ``true``
    — into a character code. The hand-rolled check rejected the string and
    accepted the bool; strict mode rejects both.
    """

    character_code: StrictInt = Field(
        ...,
        ge=0,
        le=71,
        description="Vestaboard character code to fill every flap with (0-71).",
    )


class DebugActionResponse(BaseModel):
    """A debug action that either happened or raised."""

    message: str


class DebugInfoResponse(BaseModel):
    """``POST /debug/info`` — the card that was rendered, and its text."""

    message: str
    debug_info: str


class ConnectionTestResponse(BaseModel):
    """``POST /debug/test-connection`` on the success path only.

    ``connected`` is always ``True`` here: an unreachable board is a 503
    (#1887), so this body is never the report of a failed probe. It is kept
    because the field is part of the published contract and the web client
    reads it.
    """

    message: str
    connected: bool = True
    latency_ms: int


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------


class CacheStatus(BaseModel):
    """The board client's content-dedupe cache, as every client reports it."""

    has_cached_text: bool
    has_cached_characters: bool
    skip_unchanged_enabled: bool
    cached_text_preview: str | None = None


class ForceRefreshResponse(BaseModel):
    """``POST /force-refresh`` — did the forced pass actually reach a board?"""

    message: str
    sent: bool


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------


class SystemInfoResponse(BaseModel):
    """``GET /debug/system-info`` — the support card, without sending it."""

    board_ip: str
    server_ip: str
    uptime_seconds: float | None = None
    uptime_formatted: str
    connection_mode: str
    version: str
    timestamp: str
    cache_status: CacheStatus | None = None
    board_configured: bool
    service_running: bool


# ---------------------------------------------------------------------------
# Network diagnostics
# ---------------------------------------------------------------------------


class DiagnosticStepResult(BaseModel):
    """One probe in the diagnostics run.

    Every field except ``ok`` is optional because each probe reports a
    different subset (DNS reports ``hostname``/``ip``, the port check reports
    ``host``/``port``, the HTTP checks report ``url``/``status_code``).
    ``extra="allow"`` keeps the model a faithful pass-through: a new key added
    to ``src/network_diagnostics.py`` reaches the client instead of being
    silently dropped on serialization.
    """

    model_config = ConfigDict(extra="allow")

    ok: bool
    hostname: str | None = None
    ip: str | None = None
    url: str | None = None
    host: str | None = None
    port: int | None = None
    status_code: int | None = None
    latency_ms: int | None = None
    error: str | None = None


class VestaboardDiagnostics(BaseModel):
    """The layered board check: DNS, then TCP, then the API call."""

    model_config = ConfigDict(extra="allow")

    ok: bool
    mode: str | None = None
    steps: dict[str, DiagnosticStepResult] = Field(default_factory=dict)
    error: str | None = None


class DiagnosticRecommendation(BaseModel):
    """Plain-English troubleshooting for one detected problem."""

    summary: str
    steps: list[str]


class NetworkDiagnosticsResponse(BaseModel):
    """``GET /debug/network-diagnostics`` — the runner's verdict, bare."""

    model_config = ConfigDict(extra="allow")

    dns: DiagnosticStepResult
    internet: DiagnosticStepResult
    vestaboard: VestaboardDiagnostics
    overall_ok: bool
    recommendations: list[DiagnosticRecommendation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class LogEntry(BaseModel):
    """One line of the application log, as the JSON file handler writes it."""

    model_config = ConfigDict(extra="allow")

    timestamp: str | None = None
    level: str | None = None
    logger: str | None = None
    message: str | None = None


class LogFilters(BaseModel):
    """The filters that were applied, normalized (level upper-cased)."""

    level: str | None = None
    search: str | None = None


class LogsResponse(BaseModel):
    """``GET /logs`` — one page of entries plus the cursor state."""

    logs: list[LogEntry]
    total: int
    limit: int
    offset: int
    has_more: bool
    filters: LogFilters
