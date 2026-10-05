"""Output hooks: what core asks an output instead of knowing its device.

Core used to carry device knowledge for the one device it drove — how to find
a Vestaboard on the LAN, how to diagnose one, what its probe's HTTP statuses
mean, how to exchange its Local API enablement token, how often reading it
back costs a network call. Each of those is now a question core asks *the
output* (plan D3), answered by the output's registry entry
(:class:`~src.outputs.registry.OutputDefinition`) or by its driver:

- per **output**, on the registry entry's :class:`OutputHooks` —
  ``discover(timeout)`` (find devices on the network),
  :class:`OutputDiagnostics` (the output's section of the network
  diagnostics), and named custom ``actions`` (e.g. ``enable_local_api``);
- per **board**, on the driver — :meth:`check_connection` returning a
  :class:`ConnectionCheck`, :attr:`read_back` (a :class:`ReadBack`) and
  ``connection_label``.

Every hook is optional: an output without one simply has nothing to say
(no devices to discover, no diagnostics section of its own), and core
answers the way it always answered a board with no connection.

The legacy routes (``/config/board/scan``, ``/config/board/test``,
``/config/board/enable-local-api``, ``/debug/network-diagnostics``) stay,
pinned in ``tests/golden/api_routes.json``, and delegate here (plan D8).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

#: Why a connection check failed, as a class core and the UI can branch on
#: without parsing the message: the device refused the credential (``auth``);
#: no socket could be opened (``unreachable``); the device accepted the
#: socket but never answered (``timeout``); it answered with a server error
#: (``server_error``) or a status the output does not recognise
#: (``unexpected_status``); it answered 200 with a body that is not its read
#: shape (``bad_response``); or FiestaBoard refused to contact the host at
#: all (``blocked``, ``FIESTABOARD_OUTPUTS_ALLOW_HOSTS``).
FailureClass = Literal[
    "auth",
    "unreachable",
    "timeout",
    "server_error",
    "unexpected_status",
    "bad_response",
    "blocked",
]


@dataclass(frozen=True)
class ConnectionCheck:
    """One connection probe's verdict, structured.

    ``details`` carries output-specific fields a success reports (the
    Vestaboard probe reports its ``api_mode``). :meth:`to_verdict` is the
    wire shape ``POST /config/board/test`` has always answered with.
    """

    success: bool
    message: str
    failure: FailureClass | None = None
    error: str | None = None
    troubleshooting: tuple[str, ...] | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_verdict(self) -> dict:
        """The probe's response body: ``success``, ``message``, then the
        output's ``details``, then ``error``/``troubleshooting`` when set."""
        verdict: dict[str, Any] = {"success": self.success, "message": self.message, **self.details}
        if self.error is not None:
            verdict["error"] = self.error
        if self.troubleshooting is not None:
            verdict["troubleshooting"] = list(self.troubleshooting)
        return verdict

    @classmethod
    def blocked(cls, host: str | None) -> ConnectionCheck:
        """FiestaBoard refused to contact *host*: it is outside
        ``FIESTABOARD_OUTPUTS_ALLOW_HOSTS``.

        Named plainly so a developer whose dev stack fenced off a real device
        sees why, rather than a generic "could not connect".
        """
        from src.output_allowlist import ENV_VAR

        return cls(
            success=False,
            message=f"Not contacted: {host} is not in {ENV_VAR}.",
            failure="blocked",
            error="Host not allowed",
            troubleshooting=(f"Add {host} to {ENV_VAR}, or unset it to allow every host.",),
        )


#: What reading a device's current frame back costs: a LAN round trip or an
#: in-memory read (``cheap``), or a call to a remote service (``network``).
ReadBackCost = Literal["cheap", "network"]


@dataclass(frozen=True)
class ReadBack:
    """Whether — and how often — core may read a board's frame back (plan D3).

    Core's board-state poll picks the user's *network* interval
    (``board_read_interval_cloud``) for a ``network`` read and the *cheap*
    one (``board_read_interval_local``) otherwise.
    ``suggested_interval_s`` is the driver's own default for that interval.
    """

    supported: bool
    cost: ReadBackCost
    suggested_interval_s: int


@dataclass(frozen=True)
class OutputDiagnostics:
    """An output's section of ``GET /debug/network-diagnostics``.

    ``run`` takes the saved board dict and returns the section (an ``ok``
    bool, plus whatever steps the output checks). ``advise`` turns that
    section into plain-English recommendations (``{"summary", "steps"}``).
    ``all_clear`` is the summary shown when every check — core's and the
    output's — passed.
    """

    run: Callable[[Mapping], dict]
    advise: Callable[[Mapping], list[dict]]
    all_clear: str


class OutputActionError(Exception):
    """An output action refused, or failed, with the answer to give.

    ``status_code`` and ``detail`` are handed to ``HTTPException`` verbatim by
    the route that runs the action. (``src.config_api.service.BoardProbeError``
    is this class.)
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class UnknownOutputAction(LookupError):
    """The output has no custom action by that name."""

    def __init__(self, output_id: str, action: str) -> None:
        super().__init__(f"Output '{output_id}' has no action '{action}'")
        self.output_id = output_id
        self.action = action


@dataclass(frozen=True)
class OutputHooks:
    """The per-output hooks an :class:`~src.outputs.registry.OutputDefinition`
    carries. Every member is optional."""

    #: ``discover(timeout)`` → devices found on the network, each a dict with
    #: at least ``ip`` and ``port`` (plus ``hostname`` and ``source``).
    discover: Callable[[float], list[dict]] | None = None
    diagnostics: OutputDiagnostics | None = None
    #: Named custom actions, e.g. ``{"enable_local_api": fn}``.
    actions: Mapping[str, Callable[..., Any]] = field(default_factory=dict)
    #: A built-in output's board-settings action runner: ``await
    #: dispatch(ActionCall)`` → :class:`ActionOutcome`. Output plugins need
    #: none; core dispatches to the plugin instance (``run_action``).
    dispatch: Callable[[ActionCall], Awaitable[ActionOutcome]] | None = None


# --- board settings actions (plan D13) -------------------------------------------

#: The action ids core maps to a built-in hook instead of an ``action_<id>``
#: method: ``test_connection`` → ``check_connection()``, ``discover`` →
#: ``discover(timeout)``, ``identify`` → ``identify()``, ``detect_geometry``
#: → ``detect_geometry()``. Every other declared id is a custom action.
BUILTIN_ACTION_IDS: tuple[str, ...] = ("test_connection", "discover", "identify", "detect_geometry")

#: An action's verdict.
ActionStatus = Literal["ok", "error", "warning"]


@dataclass(frozen=True)
class ActionField:
    """One value an action hands back for the settings form to fill.

    ``secret`` values are never logged and are written through the form's
    secret path (masked once saved).
    """

    value: Any
    secret: bool = False


@dataclass(frozen=True)
class ActionOutcome:
    """What an output action answers; core renders it as the closed
    ``ActionResult`` envelope (``src/outputs/models.py``).

    ``geometry`` is ``{device_type, rows, cols, notes_wide?, notes_tall?,
    matched_preset?}`` — the ``detect-size`` shape, so the apply step is the
    same. ``devices`` are dicts with at least ``ip`` and ``port``.
    """

    status: ActionStatus = "ok"
    message: str = ""
    guidance: tuple[str, ...] = ()
    fields: Mapping[str, ActionField] = field(default_factory=dict)
    geometry: Mapping[str, Any] | None = None
    devices: tuple[Mapping[str, Any], ...] | None = None

    @classmethod
    def from_check(cls, check: ConnectionCheck) -> ActionOutcome:
        """A connection probe's verdict as an action outcome."""
        return cls(
            status="ok" if check.success else "error",
            message=check.message,
            guidance=tuple(check.troubleshooting or ()),
        )


@dataclass(frozen=True)
class ActionCall:
    """One action run: which, on what board (saved or draft), with what input.

    ``board`` is the board dict the output builds a driver from — a saved
    board with any edited ``output_config`` merged in (secrets restored), or
    a draft. ``board_id`` is ``None`` for a draft.
    """

    action: str
    board: Mapping[str, Any]
    board_id: str | None
    inputs: Mapping[str, Any]


@dataclass(frozen=True)
class ResultFieldSpec:
    """A declared action result field: ``secret`` marks a credential;
    ``fills`` names the settings field the form writes it to (default: the
    result field's own name)."""

    secret: bool = False
    fills: str | None = None


@dataclass(frozen=True)
class OutputActionSpec:
    """One declared board-settings action: a button the form renders."""

    id: str
    label: str
    description: str = ""
    #: JSON Schema (the settings vocabulary) of the action's input, if any.
    input_schema: Mapping[str, Any] | None = None
    result_fields: Mapping[str, ResultFieldSpec] = field(default_factory=dict)

    @property
    def builtin(self) -> bool:
        return self.id in BUILTIN_ACTION_IDS
