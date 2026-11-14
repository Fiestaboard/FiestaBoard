"""What the in-app chat may run, checked by the hub at ``call_tool``.

The chat drives the hub through the same MCP tools an external client uses
(:mod:`src.ai.mcp_bridge`), but it is a different caller: its tool calls are
written by a model that reads untrusted text, and they arrive through a
browser route. :class:`ChatToolPolicy` holds the rules that apply to the
chat and not to ``/mcp``. :class:`PolicedToolBackend` applies them on every
call, fresh or resumed, so no path through the agent loop skips them.

Today there is one rule: **no Git installs from the chat.** ``install_plugin``
with ``repository`` (or ``branch``) clones a repository and imports it into
the hub process. That stays on the Integrations page ("Add from Git", which
calls ``POST /plugins/install``) where the user types the URL themselves.
The chat can still install from the curated registry.

A per-credential allow-list (which tools a given token scope may reach)
belongs in :meth:`ChatToolPolicy.refusal` too; it is built per request so it
can be given the caller.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .mcp_bridge import ToolBackend, ToolDescriptor, ToolOutcome

#: Arguments the chat may not pass, per tool.
CHAT_REFUSED_ARGS: dict[str, frozenset[str]] = {
    "install_plugin": frozenset({"repository", "branch"}),
}

GIT_INSTALL_REFUSAL = (
    "Installing a plugin from a Git repository is not available in chat. "
    "Use Integrations → Add from Git, or install a plugin from the registry by its id."
)


class ChatToolPolicy:
    """The chat's rules over tool names and arguments."""

    def refusal(self, name: str, args: dict[str, Any]) -> str | None:
        """Why the chat may not run ``name(args)``, or ``None`` if it may."""
        refused = CHAT_REFUSED_ARGS.get(name, frozenset())
        if any(args.get(key) not in (None, "") for key in refused):
            return GIT_INSTALL_REFUSAL
        return None

    def taught(self, descriptor: ToolDescriptor) -> ToolDescriptor:
        """The descriptor as the chat teaches it, without refused arguments."""
        refused = CHAT_REFUSED_ARGS.get(descriptor.name)
        if not refused:
            return descriptor
        schema = dict(descriptor.input_schema or {})
        schema["properties"] = {k: v for k, v in (schema.get("properties") or {}).items() if k not in refused}
        if "required" in schema:
            schema["required"] = [k for k in schema["required"] if k not in refused]
        description = descriptor.description
        if descriptor.name == "install_plugin":
            description = (
                "Install a plugin from the FiestaBoard registry by its plugin_id (from list_registry_plugins()). "
                + ("Installing from a Git URL is not available in chat; point the user to Integrations → Add from Git.")
            )
        return replace(descriptor, input_schema=schema, description=description)


class PolicedToolBackend:
    """A tool backend whose every call passes :class:`ChatToolPolicy` first."""

    def __init__(self, inner: ToolBackend, policy: ChatToolPolicy | None = None) -> None:
        self._inner = inner
        self._policy = policy or ChatToolPolicy()

    async def list_tools(self) -> list[ToolDescriptor]:
        return [self._policy.taught(d) for d in await self._inner.list_tools()]

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        reason = self._policy.refusal(name, args)
        if reason is not None:
            return ToolOutcome(status="blocked", error=reason)
        return await self._inner.call_tool(name, args)


__all__ = ["CHAT_REFUSED_ARGS", "ChatToolPolicy", "PolicedToolBackend"]
