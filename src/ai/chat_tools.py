"""Chat-only extension tools.

One tool the in-app chat needs that is deliberately **not** an MCP tool:

- ``ask_user`` — the model asks the user a question, optionally with
  choices. It is answered in the browser, never executed here, and would
  be meaningless to an external MCP client (which has its own way to ask —
  elicitation — that cannot run in-process today).

``trigger_system_update`` used to live here too; it is a real MCP tool now
(``src/mcp_server.py``), alongside ``restart_system`` and
``shutdown_system``, so external clients and the chat share one
implementation and one approval gate.

It is rendered in the same :class:`~src.ai.mcp_bridge.ToolDescriptor`
shape as the MCP catalog so the model, the parser and the UI treat every
tool alike; ``source="chat"`` is what tells it apart.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .mcp_bridge import ToolDescriptor, ToolOutcome

ASK_USER = "ask_user"


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


class ChatExtensionBackend:
    """The chat-only tools, behind the same interface as the MCP backend."""

    async def list_tools(self) -> list[ToolDescriptor]:
        return [_ASK_USER]

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        if name == ASK_USER:
            return ToolOutcome(status="error", error="ask_user is answered by the user, not executed.")
        return ToolOutcome(status="error", error=f"Unknown tool: {name}")


__all__ = ["ASK_USER", "ChatExtensionBackend"]
