"""Chat-only extension tools.

Two tools the in-app chat needs that are deliberately **not** MCP tools:

- ``ask_user`` — the model asks the user a question, optionally with
  choices. It is answered in the browser, never executed here, and would
  be meaningless to an external MCP client (which has its own way to ask —
  elicitation — that cannot run in-process today).
- ``trigger_system_update`` — pulls a new FiestaBoard image through the
  updater sidecar. It was already a chat-only operation; promoting it to
  MCP is a separate decision, so it keeps its executor and gains only the
  descriptor shape.

They are rendered in the same :class:`~src.ai.mcp_bridge.ToolDescriptor`
shape as the MCP catalog so the model, the parser and the UI treat every
tool alike; ``source="chat"`` is what tells them apart.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .mcp_bridge import ToolDescriptor, ToolOutcome

ASK_USER = "ask_user"
TRIGGER_SYSTEM_UPDATE = "trigger_system_update"


class AskUserArgs(BaseModel):
    """Arguments of the ``ask_user`` tool, as JSON Schema for the catalog."""

    question: str = Field(description="The question to put to the user, in one or two sentences.")
    options: list[str] | None = Field(
        default=None,
        description="Optional short answers to offer as one-click choices (2-6 items).",
    )
    allow_free_text: bool = Field(default=True, description="Whether the user may type an answer of their own.")


_ASK_USER = ToolDescriptor(
    name=ASK_USER,
    title="Ask the user",
    description=(
        "Ask the user a question and wait for the answer before continuing. "
        "Use it when a request is ambiguous (which board, which page, what "
        "time) instead of guessing. The answer arrives as your next message.\n\n"
        "Args:\n"
        "    question: The question to put to the user, in one or two sentences.\n"
        "    options: Optional short answers to offer as one-click choices (2-6 items).\n"
        "    allow_free_text: Whether the user may type an answer of their own (default true)."
    ),
    input_schema=AskUserArgs.model_json_schema(),
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=False,
    source="chat",
)

_TRIGGER_SYSTEM_UPDATE = ToolDescriptor(
    name=TRIGGER_SYSTEM_UPDATE,
    title="Update FiestaBoard",
    description=(
        "Pull the latest FiestaBoard release and restart. The container "
        "restarts and the web UI drops for a minute. Only call this when the "
        "user explicitly asks to update the system; it always requires their "
        "approval."
    ),
    input_schema={"type": "object", "properties": {}},
    read_only=False,
    destructive=True,
    idempotent=False,
    open_world=True,
    source="chat",
)


class ChatExtensionBackend:
    """The chat-only tools, behind the same interface as the MCP backend."""

    async def list_tools(self) -> list[ToolDescriptor]:
        return [_ASK_USER, _TRIGGER_SYSTEM_UPDATE]

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        if name == ASK_USER:
            return ToolOutcome(status="error", error="ask_user is answered by the user, not executed.")
        if name == TRIGGER_SYSTEM_UPDATE:
            from src.ops import executors

            envelope = await executors.trigger_system_update()
            if isinstance(envelope, dict) and envelope.get("status") == "error":
                return ToolOutcome(status="error", error=str(envelope.get("error") or "The update could not start."))
            return ToolOutcome(status="ok", result=envelope)
        return ToolOutcome(status="error", error=f"Unknown tool: {name}")


__all__ = ["ASK_USER", "TRIGGER_SYSTEM_UPDATE", "AskUserArgs", "ChatExtensionBackend"]
