"""The named operation set — one grammar for chat ops and MCP tools.

Issue #1764: ``src/ai/chat_ops.py`` and ``src/mcp_server.py`` grew two
parallel grammars for the same actions (``update_plugin_config`` vs
``configure_plugin``, ``replace_page`` vs ``create_page``), each with its
own implementation. This registry maps *both* name sets onto one canonical
executor per operation (:mod:`src.ops.executors`), so the surfaces cannot
diverge in behavior. Retiring the duplicate names is #1766-style follow-up
work; here both grammars stay valid.

Three kinds of operation live here:

- shared ops — a chat name and an MCP tool name resolving to one executor;
- single-surface server ops — only one grammar names them today
  (``delete_page`` is MCP-only, ``update_setting`` is chat-only);
- client-side chat ops — applied inside the web UI with no server-side
  effect (``apply_patch`` edits the editor's draft, ``navigate_to_page``
  routes). They are registered so the registry describes the *whole*
  grammar, but carry no executor.

``execute()`` is the chat-grammar entry point: given a chat op name it
validates the args against the op's chat schema (the same models
``parse_tool_call`` uses) before adapting them onto the executor. MCP
tools call the executors directly — their argument shape already is the
canonical one.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import executors


class ClientSideOperationError(LookupError):
    """Raised when execute() is asked to run an op that only the web UI applies."""


@dataclass(frozen=True)
class Operation:
    """One named operation: canonical name, aliases, validator, executor."""

    name: str
    #: Canonical executor. ``None`` only for client-side chat ops.
    executor: Callable[..., Any] | None = None
    #: The chat-grammar spelling, when the chat surface has one.
    chat_name: str | None = None
    #: The MCP tool spelling, when the MCP surface has one.
    mcp_tool: str | None = None
    #: Maps validated chat args (a pydantic model) onto executor kwargs.
    adapt_chat_args: Callable[[Any], dict[str, Any]] | None = None
    #: True for ops the web UI applies client-side (no server effect).
    client_side: bool = field(default=False)

    @property
    def aliases(self) -> set[str]:
        return {n for n in (self.name, self.chat_name, self.mcp_tool) if n}


def _model_fields(args: Any, *names: str) -> dict[str, Any]:
    """Executor kwargs from the named chat-args fields, skipping ``None``s."""
    out: dict[str, Any] = {}
    for name in names:
        value = getattr(args, name)
        if value is not None:
            out[name] = value
    return out


def _adapt_replace_page(args: Any) -> dict[str, Any]:
    """``replace_page`` materializes a full page definition → create_page.

    The chat surface knows the device from the editor context; server-side
    execution falls back to the executor's flagship default.
    """
    kwargs: dict[str, Any] = {
        "name": args.name,
        "template_lines": args.template,
        "duration_seconds": args.duration_seconds,
    }
    if args.line_metadata:
        kwargs["line_metadata"] = [m.model_dump() for m in args.line_metadata]
    return kwargs


def _adapt_install_plugin(args: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"plugin_id": args.plugin_id, "auto_enable": args.auto_enable}
    if args.initial_config:
        kwargs["initial_config"] = args.initial_config
    return kwargs


OPERATIONS: tuple[Operation, ...] = (
    # -- pages ------------------------------------------------------------
    Operation(
        name="create_page",
        executor=executors.create_page,
        chat_name="replace_page",
        mcp_tool="create_page",
        adapt_chat_args=_adapt_replace_page,
    ),
    Operation(name="update_page", executor=executors.update_page, mcp_tool="update_page"),
    Operation(name="delete_page", executor=executors.delete_page, mcp_tool="delete_page"),
    Operation(name="set_active_page", executor=executors.set_active_page, mcp_tool="set_active_page"),
    # -- schedules --------------------------------------------------------
    Operation(
        name="create_schedule",
        executor=executors.create_schedule,
        chat_name="create_schedule",
        mcp_tool="create_schedule",
        adapt_chat_args=lambda a: {
            "page_id": a.page_id,
            "start_time": a.start_time,
            "end_time": a.end_time,
            "day_pattern": a.day_pattern,
            "enabled": a.enabled,
            **({"custom_days": a.custom_days} if a.custom_days is not None else {}),
        },
    ),
    Operation(
        name="update_schedule",
        executor=executors.update_schedule,
        chat_name="update_schedule",
        mcp_tool="update_schedule",
        adapt_chat_args=lambda a: {
            "schedule_id": a.schedule_id,
            **_model_fields(a, "page_id", "start_time", "end_time", "day_pattern", "custom_days", "enabled"),
        },
    ),
    Operation(
        name="delete_schedule",
        executor=executors.delete_schedule,
        chat_name="delete_schedule",
        mcp_tool="delete_schedule",
        adapt_chat_args=lambda a: {"schedule_id": a.schedule_id},
    ),
    Operation(name="set_schedule_mode", executor=executors.set_schedule_mode, mcp_tool="set_schedule_mode"),
    # -- collections ------------------------------------------------------
    Operation(
        name="create_collection",
        executor=executors.create_collection,
        chat_name="create_collection",
        mcp_tool="create_collection",
        adapt_chat_args=lambda a: {
            "name": a.name,
            "page_ids": a.page_ids,
            "interval_seconds": a.interval_seconds,
        },
    ),
    Operation(
        name="update_collection",
        executor=executors.update_collection,
        chat_name="update_collection",
        mcp_tool="update_collection",
        adapt_chat_args=lambda a: {
            "collection_id": a.collection_id,
            **_model_fields(a, "name", "page_ids", "interval_seconds"),
        },
    ),
    Operation(name="delete_collection", executor=executors.delete_collection, mcp_tool="delete_collection"),
    # -- plugins ----------------------------------------------------------
    Operation(
        name="install_plugin",
        executor=executors.install_plugin,
        chat_name="install_plugin",
        mcp_tool="install_plugin",
        adapt_chat_args=_adapt_install_plugin,
    ),
    Operation(
        name="configure_plugin",
        executor=executors.configure_plugin,
        chat_name="update_plugin_config",
        mcp_tool="configure_plugin",
        adapt_chat_args=lambda a: {"plugin_id": a.plugin_id, "config": a.config},
    ),
    Operation(
        name="enable_plugin",
        executor=executors.enable_plugin,
        chat_name="enable_plugin",
        mcp_tool="enable_plugin",
        adapt_chat_args=lambda a: {"plugin_id": a.plugin_id},
    ),
    Operation(
        name="disable_plugin",
        executor=executors.disable_plugin,
        chat_name="disable_plugin",
        mcp_tool="disable_plugin",
        adapt_chat_args=lambda a: {"plugin_id": a.plugin_id},
    ),
    Operation(
        name="uninstall_plugin",
        executor=executors.uninstall_plugin,
        chat_name="uninstall_plugin",
        mcp_tool="uninstall_plugin",
        adapt_chat_args=lambda a: {"plugin_id": a.plugin_id},
    ),
    Operation(
        name="update_plugin",
        executor=executors.update_plugin,
        chat_name="update_plugin",
        mcp_tool="update_plugin",
        adapt_chat_args=lambda a: {"plugin_id": a.plugin_id},
    ),
    # -- settings / system ------------------------------------------------
    Operation(
        name="update_setting",
        executor=executors.update_setting,
        chat_name="update_setting",
        adapt_chat_args=lambda a: {"category": a.category, "values": a.values},
    ),
    Operation(
        name="trigger_system_update",
        executor=executors.trigger_system_update,
        chat_name="trigger_system_update",
        adapt_chat_args=lambda a: {},
    ),
    # -- client-side chat ops (no server effect) --------------------------
    Operation(name="apply_patch", chat_name="apply_patch", client_side=True),
    Operation(name="suggest_variables", chat_name="suggest_variables", client_side=True),
    Operation(name="navigate_to_page", chat_name="navigate_to_page", client_side=True),
    Operation(name="navigate_to_schedule", chat_name="navigate_to_schedule", client_side=True),
    Operation(name="update_task_list", chat_name="update_task_list", client_side=True),
)


def _build_alias_map() -> dict[str, Operation]:
    by_alias: dict[str, Operation] = {}
    for op in OPERATIONS:
        for alias in op.aliases:
            existing = by_alias.get(alias)
            if existing is not None and existing is not op:
                raise ValueError(f"operation alias collision: {alias!r} names both {existing.name} and {op.name}")
            by_alias[alias] = op
    return by_alias


_BY_ALIAS: dict[str, Operation] = _build_alias_map()


def get_operation(name: str) -> Operation:
    """Resolve either grammar's spelling to its operation."""
    op = _BY_ALIAS.get(name)
    if op is None:
        raise KeyError(f"unknown operation: {name!r}")
    return op


def operation_names() -> set[str]:
    """Every name the registry resolves (canonical + both grammars)."""
    return set(_BY_ALIAS)


async def execute(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute an operation by chat-grammar or canonical name.

    Chat names are validated against the chat-op schema first (the exact
    validation ``parse_tool_call`` applies), then adapted onto the
    canonical executor. Canonical/MCP names pass ``args`` straight through
    as executor kwargs.
    """
    op = get_operation(name)
    if op.client_side:
        raise ClientSideOperationError(
            f"operation {name!r} is applied client-side by the web UI and has no server executor"
        )
    assert op.executor is not None

    if op.chat_name is not None and name == op.chat_name:
        from src.ai.chat_ops import parse_tool_call

        validated = parse_tool_call({"op": name, "args": args})
        assert op.adapt_chat_args is not None, f"chat-named op {name!r} has no args adapter"
        kwargs = op.adapt_chat_args(validated.args)
    else:
        kwargs = dict(args)

    result = op.executor(**kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


def execute_sync(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Blocking convenience wrapper around :func:`execute`."""
    return asyncio.run(execute(name, args))
