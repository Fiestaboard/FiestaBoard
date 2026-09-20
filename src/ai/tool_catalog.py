"""The tool catalog: what the model is taught, and what the parser accepts.

Replaces the hand-written tool grammar that used to live in
:mod:`src.ai.chat`. That text described a parallel set of "chat ops" that
could — and did — drift from the MCP tools. Now the catalog is built from
the same descriptors ``MCPServer.list_tools()`` publishes, so the chat
teaches exactly the tools the MCP server serves, with the same names,
arguments and annotations.

Two jobs:

- :meth:`ToolCatalog.render_addendum` — the system-prompt section listing
  every tool. Compact on purpose (first paragraph + the docstring's
  ``Args:`` block + a generated one-line signature): the catalog is ~36
  tools and every byte is paid for on every turn.
- :meth:`ToolCatalog.validate` — the check the streaming fence parser runs
  on a completed block. Name, shape, required keys and top-level primitive
  types; anything deeper is the MCP server's pydantic validation at call
  time, which the loop feeds back to the model.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from src.ops.registry import SYSTEM_GATED

from .mcp_bridge import ToolDescriptor

ChatSurface = Literal["editor", "global"]

#: Names the chat used to accept and the model may still emit from habit.
#: Listed once in the addendum and named in the validator's rejection so the
#: closest-match hint has something to point at.
RETIRED_OPS: tuple[str, ...] = (
    "replace_page",
    "apply_patch",
    "suggest_variables",
    "navigate_to_page",
    "navigate_to_schedule",
    "update_task_list",
    "update_plugin_config",
)

_RETIRED_REPLACEMENTS = {
    "replace_page": "create_page or update_page",
    "apply_patch": "update_page",
    "suggest_variables": "get_template_variables",
    "navigate_to_page": "create_page or update_page (the app opens the page for the user)",
    "navigate_to_schedule": "create_schedule (the app opens the schedule for the user)",
    "update_task_list": "nothing — progress is shown from the tools you call",
    "update_plugin_config": "configure_plugin",
}

_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class ToolCallValidationError(ValueError):
    """A fenced block does not describe a call the catalog accepts."""


@dataclass(frozen=True)
class ParsedToolCall:
    """A validated ``{"op": ..., "args": {...}}`` block."""

    name: str
    args: dict[str, Any]


class ToolCatalog:
    """The tools one chat turn may call."""

    def __init__(self, descriptors: Iterable[ToolDescriptor]) -> None:
        self._by_name: dict[str, ToolDescriptor] = {}
        for descriptor in descriptors:
            self._by_name[descriptor.name] = descriptor

    @property
    def names(self) -> list[str]:
        return list(self._by_name)

    def get(self, name: str) -> ToolDescriptor | None:
        return self._by_name.get(name)

    # -- validation ---------------------------------------------------------

    def validate(self, payload: object) -> ParsedToolCall:
        """Check a parsed fence body against the catalog."""
        if not isinstance(payload, dict):
            raise ToolCallValidationError("Tool call must be a JSON object.")
        name = payload.get("op", payload.get("tool"))
        if not isinstance(name, str) or not name:
            raise ToolCallValidationError("Tool call is missing the required 'op' string.")
        descriptor = self._by_name.get(name)
        if descriptor is None:
            raise ToolCallValidationError(self._unknown_tool_message(name))
        args = payload.get("args", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ToolCallValidationError("'args' must be a JSON object.")

        schema = descriptor.input_schema or {}
        properties = schema.get("properties") or {}
        missing = [key for key in schema.get("required") or [] if key not in args]
        if missing:
            raise ToolCallValidationError(f"{name} is missing required args: {', '.join(missing)}.")
        for key, value in args.items():
            expected = (properties.get(key) or {}).get("type")
            py_type = _JSON_TYPES.get(expected) if isinstance(expected, str) else None
            if py_type is None or value is None:
                continue
            if isinstance(value, bool) and py_type in (int, (int, float)):
                # JSON booleans are not numbers, whatever Python thinks.
                raise ToolCallValidationError(f"{name}.{key} must be a {expected}, got a boolean.")
            if not isinstance(value, py_type):
                raise ToolCallValidationError(f"{name}.{key} must be a {expected}, got {type(value).__name__}.")
        return ParsedToolCall(name=name, args=dict(args))

    def _unknown_tool_message(self, name: str) -> str:
        if name in _RETIRED_REPLACEMENTS:
            return f"Unknown tool {name!r}: that op was retired. Use {_RETIRED_REPLACEMENTS[name]} instead."
        closest = difflib.get_close_matches(name, self.names, n=3, cutoff=0.5)
        hint = f" Closest: {', '.join(closest)}." if closest else ""
        return f"Unknown tool {name!r}.{hint}"

    # -- the taught text ----------------------------------------------------

    def render_addendum(self, surface: ChatSurface, *, skip_destructive_pause: bool = False) -> str:
        """The system-prompt section that teaches the tools.

        ``skip_destructive_pause`` is the effective approval policy (#2021):
        the install is in Auto, or the conversation said "don't ask again".
        The model is then told destructive tools run immediately — except
        the system tier, which is described as gated in every mode — so it
        does not narrate a pause that will not happen.
        """
        intro = _EDITOR_SURFACE_INTRO if surface == "editor" else _GLOBAL_SURFACE_INTRO
        sections = [_render_tool(d, skip_destructive_pause) for d in self._by_name.values()]
        retired = ", ".join(RETIRED_OPS)
        destructive_rule = _RULE_DESTRUCTIVE_AUTO if skip_destructive_pause else _RULE_DESTRUCTIVE_ASK
        return (
            "\n\nCHAT MODE — TOOLS\n\n"
            + intro
            + _HOW_TO_CALL
            + _RULES_HEAD
            + destructive_rule
            + _RULES_TAIL
            + f"\nRETIRED (never emit these): {retired}.\n"
            + "\nAVAILABLE TOOLS\n\n"
            + "\n".join(sections)
        )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


_EDITOR_SURFACE_INTRO = (
    "SURFACE — You are the chat panel inside the page editor. The user is\n"
    "editing one page, sent above as `current_page`. If it has an `id`, the\n"
    "page is saved: call update_page with that id to change it. If it has\n"
    "no `id`, it is an unsaved draft: call create_page with the whole\n"
    "template (their draft plus your change) — the app opens the saved page\n"
    "and drops the draft. Only make a second page when they clearly ask\n"
    "for a new one.\n"
)

_GLOBAL_SURFACE_INTRO = (
    "SURFACE — You are the global chat drawer, available on every screen.\n"
    "There may be no page in focus. When the user asks to make, build or\n"
    "design something, call create_page — the app opens the result for\n"
    "them. Use update_page only when `current_page` is present and they\n"
    "are iterating on it.\n"
)

_HOW_TO_CALL = (
    "\nTo act, emit a fenced JSON block with the language tag `fiestaboard`:\n\n"
    "```fiestaboard\n"
    '{"op": "create_page", "args": {"name": "Morning", "template_lines": ["HELLO"]}}\n'
    "```\n"
)

_RULES_HEAD = (
    "\nRULES\n"
    "- One tool block per response, unless the tool is read-only — then you\n"
    "  may call several. Read-only tools are free: call them before guessing\n"
    "  what exists.\n"
    "- Each tool's result comes back to you as a user message starting with\n"
    '  "[Tool result]". It is automated, not a new request: read it and\n'
    "  continue the task or summarise what was done. Do not narrate every\n"
    "  step.\n"
)

_RULE_DESTRUCTIVE_ASK = (
    "- Tools marked DESTRUCTIVE pause until the user approves. Tools marked\n"
    '  SYSTEM always do. A result of "denied" means do not retry; ask how\n'
    "  to proceed.\n"
)

_RULE_DESTRUCTIVE_AUTO = (
    "- Tools marked DESTRUCTIVE run immediately in this conversation: the\n"
    "  user chose not to be asked. Tools marked SYSTEM (restart, shutdown,\n"
    '  update) still pause until the user approves. A result of "denied"\n'
    "  means do not retry; ask how to proceed.\n"
)

_RULES_TAIL = (
    '- "interrupted" means the user stopped you while that tool was running;\n'
    "  check with a read-only tool before repeating a non-idempotent call.\n"
    # A FiestaPanel's grid is auto-fit from a TV's diagonal, so the model
    # cannot know it — and the flagship default silently authors a page that
    # renders one Note wide on the panel.
    "- A page is authored for one board shape. For a FiestaPanel, take that\n"
    "  shape from list_panels first — never the flagship default.\n"
    "- Use ask_user when a request is ambiguous instead of guessing.\n"
    "- Never guess API keys or credentials; ask the user for them.\n"
)


def _render_tool(d: ToolDescriptor, skip_destructive_pause: bool = False) -> str:
    if d.read_only:
        marker = "[read-only: runs immediately]"
    elif d.requires_approval and d.name in SYSTEM_GATED:
        marker = "[DESTRUCTIVE, SYSTEM: the user must approve before it runs, in every mode]"
    elif d.requires_approval and skip_destructive_pause:
        marker = "[DESTRUCTIVE: runs immediately — the user chose not to be asked; they see it happen]"
    elif d.requires_approval:
        marker = "[DESTRUCTIVE: the user must approve before it runs]"
    else:
        marker = "[writes: runs immediately; the user sees it happen]"
    description = _compact_description(d.description)
    signature = _signature_line(d.input_schema)
    lines = [f"### {d.name} — {d.title}", marker]
    if description:
        lines.append(description)
    if signature:
        lines.append(f"Args: {signature}")
    return "\n".join(lines) + "\n"


def _compact_description(description: str) -> str:
    """First paragraph plus the ``Args:`` block, nothing else.

    FastMCP ships the whole docstring as the description, and the ``Args:``
    text is the only place parameters are explained (the JSON Schema has no
    per-property descriptions). Trailing paragraphs — return shapes, tips —
    are useful to a human reader but cost tokens on every turn.
    """
    text = (description or "").strip()
    if not text:
        return ""
    paragraphs = re.split(r"\n\s*\n", text)
    first = " ".join(line.strip() for line in paragraphs[0].splitlines())
    args_block = next((p for p in paragraphs[1:] if p.lstrip().startswith("Args:")), None)
    if args_block is None:
        return first
    args_lines = [line.strip() for line in args_block.splitlines()]
    return first + "\n" + "\n".join(args_lines)


def _signature_line(schema: dict[str, Any]) -> str:
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parts: list[str] = []
    for key, spec in properties.items():
        spec = spec if isinstance(spec, dict) else {}
        type_name = _type_name(spec)
        if key in required:
            parts.append(f"{key}*: {type_name}")
        elif "default" in spec:
            parts.append(f"{key}?: {type_name} = {json.dumps(spec['default'])}")
        else:
            parts.append(f"{key}?: {type_name}")
    return ", ".join(parts)


def _type_name(spec: dict[str, Any]) -> str:
    if "enum" in spec:
        return " | ".join(json.dumps(v) for v in spec["enum"])
    type_ = spec.get("type")
    if type_ == "array":
        items = spec.get("items")
        return f"array of {_type_name(items)}" if isinstance(items, dict) else "array"
    if isinstance(type_, list):
        return " | ".join(str(t) for t in type_ if t != "null") or "any"
    if isinstance(type_, str):
        return type_
    any_of = spec.get("anyOf")
    if isinstance(any_of, list):
        names = [_type_name(s) for s in any_of if isinstance(s, dict) and s.get("type") != "null"]
        return " | ".join(dict.fromkeys(names)) or "any"
    return "any"


__all__ = ["RETIRED_OPS", "ParsedToolCall", "ToolCallValidationError", "ToolCatalog"]
