"""The chat's seam onto the MCP server.

The in-app chat drives FiestaBoard through the same tools external MCP
clients use — the in-process :class:`mcp.server.MCPServer` built by
:mod:`src.mcp_server` — so there is one implementation of every operation
and one description of it. This module is the only chat-side code that
knows the ``mcp`` package; everything crosses the seam as plain
dataclasses (:class:`ToolDescriptor` in, :class:`ToolOutcome` out) so the
agent loop and its tests never touch SDK types.

Why in-process and not HTTP loopback: ``/api/mcp/`` sits behind the bearer
token, and a loopback call would have to mint or read one for a request
that already passed session auth. ``MCPServer.list_tools()`` and
``call_tool()`` are public SDK methods; the transport adds nothing the chat
needs.

Two SDK facts shape the mapping (verified against ``mcp`` 2.x):

- ``call_tool()`` **raises** ``ToolError`` for a domain failure *and* for
  an argument-validation failure, with the message prefixed
  ``Error executing tool <name>:``. The ``isError`` result shape only
  exists on the transport. So the bridge catches, strips, and bounds.
- A tool whose return annotation is not a plain ``dict`` has its value
  wrapped as ``{"result": ...}`` in ``structuredContent``; the bridge
  unwraps that single-key envelope so ``list_pages`` yields a list.

The ``mcp`` import stays lazy — inside :meth:`McpToolBackend._server` —
because ``src.api_server`` must not pay the package's import cost at boot
(``tests/test_mcp_lazy_mount.py``). The first chat turn pays it instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

#: Longest error text forwarded to the model / the UI. Validation errors
#: from pydantic can run to many lines; the field names are what the model
#: needs to self-correct, not the "For further information visit" tail.
MAX_ERROR_CHARS = 600

#: How long a single tool call may run. ``install_plugin`` / ``update_plugin``
#: clone from a git remote and are the slow ones; everything else is local.
DEFAULT_TOOL_TIMEOUT_SECONDS = 90.0

ToolSource = Literal["mcp", "chat"]
# ``denied`` never comes from a backend: the agent records it when the user
# refuses a destructive call, in the same outcome shape so one helper renders
# every ``tool`` message.
OutcomeStatus = Literal["ok", "blocked", "error", "denied"]


@dataclass(frozen=True)
class ToolDescriptor:
    """One callable tool as the model will be taught it."""

    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool
    source: ToolSource

    @property
    def requires_approval(self) -> bool:
        """Whether the chat must pause for the user before running this."""
        return self.destructive and not self.read_only


@dataclass(frozen=True)
class ToolOutcome:
    """What happened when a tool ran, in the shape the stream reports."""

    status: OutcomeStatus
    result: Any = None
    error: str | None = None


class ToolBackendUnavailable(RuntimeError):
    """The MCP server could not be built (the ``mcp`` package is missing)."""


class ToolBackend(Protocol):
    """What the agent loop needs from wherever tools come from."""

    async def list_tools(self) -> list[ToolDescriptor]: ...

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome: ...


# ---------------------------------------------------------------------------
# Pure mappings — SDK wire dicts in, dataclasses out
# ---------------------------------------------------------------------------


def descriptor_from_wire(tool: dict[str, Any], *, source: ToolSource = "mcp") -> ToolDescriptor:
    """Build a descriptor from ``Tool.model_dump(by_alias=True)``.

    Reads the wire names (``readOnlyHint``), never the SDK attribute names,
    which changed between SDK 2.1 and 2.2. A missing annotation takes the
    spec's own defaults — read-only *false*, destructive *true*, open-world
    *true* — so an unclassified tool errs on the side of asking.
    """
    annotations = tool.get("annotations") or {}
    read_only = bool(annotations.get("readOnlyHint", False))
    return ToolDescriptor(
        name=tool["name"],
        title=(annotations.get("title") or tool.get("title") or tool["name"]),
        description=tool.get("description") or "",
        input_schema=tool.get("inputSchema") or {"type": "object", "properties": {}},
        read_only=read_only,
        destructive=bool(annotations.get("destructiveHint", not read_only)),
        idempotent=bool(annotations.get("idempotentHint", read_only)),
        open_world=bool(annotations.get("openWorldHint", True)),
        source=source,
    )


def outcome_from_call_tool_result(result: dict[str, Any]) -> ToolOutcome:
    """Map ``CallToolResult.model_dump(by_alias=True)`` to an outcome."""
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    if result.get("isError"):
        return ToolOutcome(status="error", error=_bounded(" ".join(texts) or "The tool reported an error."))

    payload: Any = result.get("structuredContent")
    if payload is None:
        joined = "\n".join(texts)
        try:
            payload = json.loads(joined) if joined else None
        except json.JSONDecodeError:
            payload = {"text": joined}
    elif isinstance(payload, dict) and set(payload) == {"result"}:
        # FastMCP wraps non-dict returns (lists, unions) as {"result": X}.
        payload = payload["result"]

    if isinstance(payload, dict) and payload.get("status") == "blocked":
        return ToolOutcome(status="blocked", result=payload)
    return ToolOutcome(status="ok", result=payload)


_TOOL_ERROR_PREFIX = re.compile(r"^Error executing tool \S+:\s*")


def outcome_from_tool_error(name: str, message: str) -> ToolOutcome:
    """Map a raised ``ToolError`` to an error outcome the model can act on.

    Strips the SDK's ``Error executing tool <name>:`` prefix (the outcome
    already names the tool), collapses pydantic's multi-line validation
    report to one line so it survives the SSE frame and the transcript,
    and drops the "For further information visit" trailer.
    """
    text = _TOOL_ERROR_PREFIX.sub("", message or "", count=1)
    text = re.sub(r"\s*For further information visit\S*", "", text)
    text = re.sub(r"\s+", " ", text).strip() or f"{name} failed."
    return ToolOutcome(status="error", error=_bounded(text))


def _bounded(text: str) -> str:
    return text if len(text) <= MAX_ERROR_CHARS else text[: MAX_ERROR_CHARS - 1] + "…"


# ---------------------------------------------------------------------------
# The in-process MCP server
# ---------------------------------------------------------------------------


def _default_server_factory() -> Any:
    from src.mcp_server import mcp_server

    return mcp_server


class McpToolBackend:
    """Tools served by the in-process MCP server."""

    def __init__(
        self,
        *,
        server: Any = None,
        server_factory: Callable[[], Any] = _default_server_factory,
        timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
    ) -> None:
        self._server = server
        self._server_factory = server_factory
        self._timeout = timeout_seconds
        self._catalog: list[ToolDescriptor] | None = None

    def _get_server(self) -> Any:
        if self._server is None:
            self._server = self._server_factory()
        if self._server is None:
            raise ToolBackendUnavailable("The MCP server is not available (is the `mcp` package installed?).")
        return self._server

    async def list_tools(self) -> list[ToolDescriptor]:
        # The catalog is static for the life of the process; the descriptions
        # are docstrings and the annotations are decorator flags.
        if self._catalog is None:
            server = self._get_server()
            tools = await server.list_tools()
            self._catalog = [descriptor_from_wire(t.model_dump(by_alias=True, exclude_none=True)) for t in tools]
        return self._catalog

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        server = self._get_server()
        try:
            from mcp.server.mcpserver.exceptions import ToolError
            from mcp.types import InputRequiredResult
        except ImportError as exc:  # pragma: no cover — the server import above would have failed first
            raise ToolBackendUnavailable(str(exc)) from exc

        try:
            result = await asyncio.wait_for(server.call_tool(name, args), timeout=self._timeout)
        except ToolError as exc:
            return outcome_from_tool_error(name, str(exc))
        except TimeoutError:
            logger.warning("MCP tool %s timed out after %.0fs", name, self._timeout)
            return ToolOutcome(status="error", error=f"{name} timed out after {self._timeout:.0f} seconds.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Mirrors _tool_failure in src/mcp_server.py: traceback to the
            # log, a one-liner with no internal detail to the caller.
            logger.exception("MCP tool %s failed unexpectedly", name)
            return ToolOutcome(status="error", error=f"{name} failed unexpectedly ({type(exc).__name__}).")

        if isinstance(result, InputRequiredResult):
            # Session-less elicitation exists in the SDK but no FiestaBoard
            # tool uses it yet; report it rather than crash the turn.
            return ToolOutcome(
                status="error",
                error=f"{name} asked for interactive input, which the chat cannot provide yet.",
            )
        return outcome_from_call_tool_result(result.model_dump(by_alias=True, exclude_none=True))


# ---------------------------------------------------------------------------
# Composite: several backends behind one catalog
# ---------------------------------------------------------------------------


class CompositeToolBackend:
    """MCP tools plus the chat-only extensions, one namespace."""

    def __init__(self, *backends: ToolBackend) -> None:
        self._backends = backends
        self._owner: dict[str, ToolBackend] | None = None

    async def list_tools(self) -> list[ToolDescriptor]:
        descriptors: list[ToolDescriptor] = []
        owner: dict[str, ToolBackend] = {}
        for backend in self._backends:
            for descriptor in await backend.list_tools():
                if descriptor.name in owner:
                    raise ValueError(f"tool name {descriptor.name!r} is provided by more than one backend")
                owner[descriptor.name] = backend
                descriptors.append(descriptor)
        self._owner = owner
        return descriptors

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        if self._owner is None:
            await self.list_tools()
        assert self._owner is not None
        backend = self._owner.get(name)
        if backend is None:
            return ToolOutcome(status="error", error=f"Unknown tool: {name}")
        return await backend.call_tool(name, args)


__all__ = [
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    "CompositeToolBackend",
    "McpToolBackend",
    "ToolBackend",
    "ToolBackendUnavailable",
    "ToolDescriptor",
    "ToolOutcome",
    "descriptor_from_wire",
    "outcome_from_call_tool_result",
    "outcome_from_tool_error",
]
