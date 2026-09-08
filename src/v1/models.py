"""Wire models unique to the ``/v1`` surface.

v1 is an adapter, so most of it reuses the models the domains already
publish — ``Page``, ``ScheduleEntry``/``ScheduleResponse``, ``Collection``,
``PluginDetail``, ``TemplateRenderResponse``, ``HealthResponse``,
``StatusResponse``. What lives here is only the genuinely new shapes: the
merged board view, the one message body that replaced five write endpoints,
and the two merged catalogues.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator

#: Highest valid flap code. 0-71 covers blank, the alphabet, digits,
#: punctuation and the eight colour tiles.
MAX_CHARACTER_CODE = 71

#: One flap. ``StrictInt`` because ``isinstance(True, int)`` is true, and a
#: JSON ``true`` silently filling a board with code 1 is exactly the hole the
#: debug endpoint's hand-rolled check left open (#1887 review).
FlapCode = Annotated[StrictInt, Field(ge=0, le=MAX_CHARACTER_CODE)]

#: Revert behaviour when a timed message expires, mirroring
#: ``VALID_REVERT_MODES`` in :mod:`src.settings.service`.
RevertMode = Literal["schedule", "page", "blank"]


class BoardSummary(BaseModel):
    """One board, as a consumer needs to see it.

    A deliberate projection, not the stored entry: ``GET /settings/board``
    serves connection credentials (masked) and per-tile wiring, none of which
    a consumer writing to a board has any use for.
    """

    id: str = Field(description="The board's stable id. Usable anywhere {board} appears in a v1 path.")
    name: str = Field(description="Human-readable board name, as set in Settings.")
    device_type: str = Field(description='Board hardware: "flagship", "note", or "note_array".')
    rows: int = Field(description="Grid height in flaps.")
    cols: int = Field(description="Grid width in flaps.")
    is_primary: bool = Field(description='True for the board that the alias "primary" resolves to.')
    paused: bool = Field(description="While true, FiestaBoard writes nothing to this board from any code path.")
    schedule_enabled: bool = Field(description="Whether this board follows its schedule rather than a fixed page.")


class BoardListResponse(BaseModel):
    """``GET /v1/boards``."""

    boards: list[BoardSummary]
    total: int


class BoardDetail(BoardSummary):
    """One board plus what is on it right now.

    The merge named in the design: ``GET /board/current-message`` (what the
    flaps show), ``GET /settings/active-page`` (the sticky manual selection)
    and ``GET /schedules/active/page`` (what the schedule says) answered as
    one document, because "what is this board doing" is one question.
    """

    characters: list[list[int]] | None = Field(
        default=None,
        description="The flap codes currently on the board, or null if nothing has been sent to it yet.",
    )
    text: str | None = Field(
        default=None,
        description="``characters`` decoded back to text, for reading. Null when ``characters`` is null.",
    )
    expected_characters: list[list[int]] | None = Field(
        default=None,
        description=(
            "The flap grid FiestaBoard last sent to this board. When it differs from ``characters`` the board "
            "has drifted from what was sent — a flap that did not turn, or something else writing to the board. "
            "Null until this instance has sent anything."
        ),
    )
    read_at: str | None = Field(
        default=None,
        description="When ``characters`` was read from the board (ISO 8601). Null for a live read.",
    )
    active_page_id: str | None = Field(
        default=None,
        description="The page or collection pinned to this board by hand, if any.",
    )
    scheduled_page_id: str | None = Field(
        default=None,
        description="The page the schedule selects for right now. Null when scheduling is off or nothing matches.",
    )
    resolved_page_id: str | None = Field(
        default=None,
        description="The page actually being displayed, with any collection resolved to a member page.",
    )
    resolved_next_check_seconds: int | None = Field(
        default=None,
        description=(
            "Seconds until ``resolved_page_id`` may change on its own, when it came from a collection that "
            "rotates. Poll again after this long rather than on a guessed timer. Null for a plain page and for "
            "a collection that cannot rotate."
        ),
    )
    source: Literal["manual", "schedule", "none"] = Field(
        description="Where ``resolved_page_id`` came from.",
    )
    default_page_id: str | None = Field(
        default=None,
        description="The page shown when the schedule has a gap.",
    )
    override_expires_at: str | None = Field(
        default=None,
        description="When the active timed message expires (ISO 8601), or null if none is running.",
    )


class BoardUpdate(BaseModel):
    """``PATCH /v1/boards/{board}`` — every field optional, only what you send is applied."""

    name: str | None = Field(default=None, min_length=1, max_length=100, description="Rename the board.")
    paused: StrictBool | None = Field(
        default=None,
        description="Pause or resume the board. While paused nothing is written to it from any code path.",
    )
    schedule_enabled: StrictBool | None = Field(
        default=None,
        description="Turn this board's schedule on or off.",
    )
    default_page_id: str | None = Field(
        default=None,
        description="Page shown when the schedule has a gap. Send null to clear it.",
    )


class TransitionOverride(BaseModel):
    """Per-send transition animation, overriding the install's settings."""

    strategy: str | None = Field(default=None, description='Transition strategy name, e.g. "instant" or "wipe".')
    interval_ms: int | None = Field(default=None, ge=0, le=5000, description="Milliseconds between animation steps.")
    step_size: int | None = Field(default=None, ge=1, description="Flaps advanced per animation step.")


class MessageRequest(BaseModel):
    """``POST /v1/boards/{board}/message`` — the front door.

    Exactly one of ``text``, ``lines``, ``characters``, ``page_id`` or
    ``fill`` says *what* to show. Everything else says how long and how.
    """

    text: str | None = Field(
        default=None,
        description="Plain text, word-wrapped to the board. Colour and character markers ({red}, {63}) work here.",
    )
    lines: list[str] | None = Field(
        default=None,
        description="One string per board row, laid out without re-wrapping across rows.",
    )
    characters: list[list[FlapCode]] | None = Field(
        default=None,
        description="A raw flap grid, sized exactly to the board. Codes are 0-71.",
    )
    page_id: str | None = Field(
        default=None,
        description="Render a saved page (or collection) and send the result.",
    )
    fill: FlapCode | None = Field(
        default=None,
        description="Fill the whole board with one flap code (0-71). 0 blanks it.",
    )

    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=480,
        description=(
            "Show this for N minutes, then revert. Omit for a message that stays until something else replaces it."
        ),
    )
    revert_mode: RevertMode | None = Field(
        default=None,
        description='What to show when a timed message expires. Requires duration_minutes. Defaults to "schedule".',
    )
    revert_page_id: str | None = Field(
        default=None,
        description='The page to revert to. Required when revert_mode is "page".',
    )
    transition: TransitionOverride | None = Field(
        default=None,
        description="Override the install's transition animation for this one send.",
    )
    force: StrictBool = Field(
        default=False,
        description="Send even when the board already shows this exact content, which is normally skipped.",
    )

    @model_validator(mode="after")
    def _exactly_one_content_field(self) -> MessageRequest:
        supplied = [
            name
            for name, value in (
                ("text", self.text),
                ("lines", self.lines),
                ("characters", self.characters),
                ("page_id", self.page_id),
                ("fill", self.fill),
            )
            if value is not None
        ]
        if len(supplied) != 1:
            raise ValueError(
                "Supply exactly one of text, lines, characters, page_id or fill "
                f"(got {', '.join(supplied) if supplied else 'none'})"
            )
        return self


class MessageResponse(BaseModel):
    """What a v1 board write actually did.

    ``sent`` is the honest answer, not an acknowledgement: it is false when
    the install's output target is UI-only, when the board already showed
    this exact content, and when a timed message was queued for the display
    loop rather than written on the spot. ``reason`` names which.
    """

    sent: bool = Field(description="True only when flaps were written to the physical board by this request.")
    board_id: str = Field(description="The board this went to, with the 'primary' alias already resolved.")
    characters: list[list[int]] = Field(description="The flap grid this request produced, sent or not.")
    text: str = Field(description="``characters`` decoded back to text, for logs and confirmations.")
    expires_at: str | None = Field(
        default=None,
        description="When a timed message reverts (ISO 8601). Null for a message with no duration.",
    )
    reason: str | None = Field(
        default=None,
        description="Why nothing was written, when sent is false. Null when sent is true.",
    )


class ActivePageRequest(BaseModel):
    """``PUT /v1/boards/{board}/active-page``."""

    page_id: str | None = Field(
        description="Page or collection to pin to this board. Send null to unpin and fall back to the schedule.",
    )


class ActivePageResponse(BaseModel):
    """The result of pinning a page to a board."""

    board_id: str
    page_id: str | None = Field(description="What is now pinned. Null means nothing is.")
    sent: bool = Field(description="Whether the new page reached the board immediately.")
    error: str | None = Field(
        default=None,
        description=(
            "Why the page did not reach the board, when ``sent`` is false. The selection is stored either way, "
            "so a 200 here is not on its own proof that anything was displayed (#1791)."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal problems, e.g. collection members that do not fit this board.",
    )


class PluginEntry(BaseModel):
    """One plugin in the merged catalogue.

    ``GET /plugins`` and ``GET /displays`` are the same registry listing seen
    twice — ``/displays`` is a four-field projection of it. v1 publishes one
    catalogue, with the display projection's ``available`` folded in.
    """

    id: str = Field(description="Plugin id. Usable anywhere {plugin} appears in a v1 path.")
    name: str
    version: str
    description: str = ""
    author: str = ""
    category: str | None = None
    plugin_type: str = Field(default="data", description='"data" for a content source, "transition" for an animation.')
    icon: str | None = None
    enabled: bool = Field(description="Whether this plugin runs and contributes template variables.")
    configured: bool = Field(description="Whether its required settings have been filled in.")


class PluginListResponse(BaseModel):
    """``GET /v1/plugins``."""

    plugins: list[PluginEntry]
    total: int
    enabled_count: int


class PluginUpdate(BaseModel):
    """``PATCH /v1/plugins/{plugin}``.

    Collapses ``POST /plugins/{plugin_id}/enable``,
    ``POST /plugins/{plugin_id}/disable`` and ``PUT /plugins/{plugin_id}/config``
    into one call. ``config`` stays a free-form map on purpose: a typed body would
    reject the ``"***"`` sentinel the API serves in place of a stored secret,
    which is what a client round-trips when it edits one field of a form.
    """

    enabled: StrictBool | None = Field(default=None, description="Enable or disable the plugin.")
    config: dict[str, Any] | None = Field(
        default=None,
        description='Replace the plugin\'s settings. Send "***" for a secret you do not want to change.',
    )


class PluginData(BaseModel):
    """``GET /v1/plugins/{plugin}/data`` — the merge of the raw and formatted reads."""

    plugin_id: str
    available: bool = Field(description="False when the plugin is disabled, unconfigured, or its fetch failed.")
    data: dict[str, Any] | None = Field(default=None, description="The plugin's own variable payload.")
    lines: list[str] = Field(
        default_factory=list,
        description="The plugin's board-ready lines, as GET /displays/{type} served them.",
    )
    text: str = Field(default="", description="``lines`` joined with newlines.")
    error: str | None = Field(default=None, description="Why the data is unavailable, when it is.")


class VariableCatalog(BaseModel):
    """``GET /v1/variables`` — every name a template may use, from both sources.

    Merges ``GET /templates/variables`` (the engine's vocabulary plus the
    static colour, symbol and filter tables) with ``GET
    /plugins/variables/all`` (what installed plugins contribute). They were
    two endpoints answering one question.
    """

    variables: dict[str, list[str]] = Field(description="Variable names grouped by their source namespace.")
    max_lengths: dict[str, int] = Field(description="Longest value each variable can render to, for layout.")
    variable_metadata: dict[str, Any] = Field(default_factory=dict, description="Per-variable descriptions and types.")
    variable_groups: dict[str, Any] = Field(default_factory=dict, description="Display grouping for editors.")
    colors: dict[str, int] = Field(description='Colour names to flap codes, e.g. {"red": 63}.')
    symbols: list[str] = Field(description="Symbol names usable as {sun}, {star} and so on.")
    filters: list[str] = Field(description="Filters usable after a variable, e.g. {{x|pad:5}}.")
    formatting: dict[str, Any] = Field(description="Layout helpers such as fill_space.")
    syntax_examples: dict[str, str] = Field(description="Worked examples of the template syntax.")
    plugin_system_enabled: bool = Field(description="False when the plugin subsystem is unavailable on this install.")


class RenderRequest(BaseModel):
    """``POST /v1/render`` — render a template without saving or sending it."""

    template: str | list[str] = Field(
        description="A template string, or one string per board row. A list is padded to the board's height.",
    )
    line_metadata: list[dict[str, Any]] | None = Field(
        default=None,
        description="Per-line alignment and wrap options, one entry per line.",
    )
