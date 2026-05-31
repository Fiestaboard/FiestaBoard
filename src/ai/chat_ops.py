"""Tool grammar for the streaming AI chat.

The chat lets a model emit one or more ``fiestaboard`` fenced JSON blocks
inline with its prose. Each block is a structured *operation* that the
editor applies to the page in flight.

We deliberately do **not** use a provider's native tool/function-calling
API: many OpenAI-compatible servers (Ollama, LM Studio, older OpenRouter
routes) silently ignore the ``tools`` field, and the Anthropic adapter
in :mod:`src.ai.protocols` doesn't yet plumb ``tool_use`` content blocks
through streaming. A fenced JSON convention works identically across
every provider we support.

The server validates each block against the schemas below as the fence
closes, and re-emits the validated payload as an ``event: tool_call``
SSE frame to the frontend.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

Alignment = Literal["left", "center", "right"]


# ---------------------------------------------------------------------------
# Line-metadata block, shared by replace_page and the line-level patch ops.
# ---------------------------------------------------------------------------


class LineMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alignment: Alignment = "left"
    wrap: bool = False


# ---------------------------------------------------------------------------
# replace_page — wholesale page replacement (same shape as the legacy
# ``/pages/ai/generate`` response). Used when the user asks for a brand-new
# page or a full rewrite.
# ---------------------------------------------------------------------------


class ReplacePageArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=100)
    template: list[str] = Field(..., min_length=1)
    line_metadata: list[LineMetadata] = Field(default_factory=list)
    duration_seconds: int = Field(300, ge=10, le=3600)


class ReplacePageOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["replace_page"]
    args: ReplacePageArgs


# ---------------------------------------------------------------------------
# apply_patch — line-level edits to the current page.
# ---------------------------------------------------------------------------


class ReplaceLineOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["replace_line"]
    index: int = Field(..., ge=0)
    text: str
    alignment: Alignment | None = None
    wrap: bool | None = None


class InsertLineOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["insert_line"]
    index: int = Field(..., ge=0)
    text: str
    alignment: Alignment | None = None
    wrap: bool | None = None


class DeleteLineOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["delete_line"]
    index: int = Field(..., ge=0)


class UpdateLineMetadataOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["update_line_metadata"]
    index: int = Field(..., ge=0)
    alignment: Alignment | None = None
    wrap: bool | None = None


LineOp = ReplaceLineOp | InsertLineOp | DeleteLineOp | UpdateLineMetadataOp


class ApplyPatchArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    changes: list[LineOp] = Field(default_factory=list)
    rename: str | None = Field(default=None, max_length=100)


class ApplyPatchOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["apply_patch"]
    args: ApplyPatchArgs


# ---------------------------------------------------------------------------
# suggest_variables — read-only, surfaces plugin variables to the user.
# ---------------------------------------------------------------------------


class VariableSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: str = Field(..., description="Variable reference like 'plugin.field'.")
    description: str | None = None
    example: str | None = None


class SuggestVariablesArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    suggestions: list[VariableSuggestion] = Field(default_factory=list)


class SuggestVariablesOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["suggest_variables"]
    args: SuggestVariablesArgs


# ---------------------------------------------------------------------------
# navigate_to_page — send the user to a page editor without editing content.
# ---------------------------------------------------------------------------


class NavigateToPageArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_id: str = Field(..., description="Existing page ID, or 'new' to create.")
    device_type: str | None = Field(default=None)


class NavigateToPageOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["navigate_to_page"]
    args: NavigateToPageArgs


# ---------------------------------------------------------------------------
# install_plugin — install a plugin from the official registry.
# ---------------------------------------------------------------------------


class InstallPluginArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugin_id: str = Field(..., min_length=1, max_length=100)
    source: Literal["registry"] = "registry"
    auto_enable: bool = True
    initial_config: dict[str, Any] | None = None


class InstallPluginOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["install_plugin"]
    args: InstallPluginArgs


# ---------------------------------------------------------------------------
# update_plugin_config — change settings for an already-installed plugin.
# ---------------------------------------------------------------------------


class UpdatePluginConfigArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugin_id: str = Field(..., min_length=1, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdatePluginConfigOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["update_plugin_config"]
    args: UpdatePluginConfigArgs


# ---------------------------------------------------------------------------
# enable_plugin — enable an already-installed but currently-disabled plugin.
# ---------------------------------------------------------------------------


class EnablePluginArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugin_id: str = Field(..., min_length=1, max_length=100)


class EnablePluginOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["enable_plugin"]
    args: EnablePluginArgs


# ---------------------------------------------------------------------------
# disable_plugin — disable an installed plugin without uninstalling it.
# ---------------------------------------------------------------------------


class DisablePluginArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugin_id: str = Field(..., min_length=1, max_length=100)


class DisablePluginOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["disable_plugin"]
    args: DisablePluginArgs


# ---------------------------------------------------------------------------
# uninstall_plugin — permanently remove an installed plugin.
# ---------------------------------------------------------------------------


class UninstallPluginArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugin_id: str = Field(..., min_length=1, max_length=100)


class UninstallPluginOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["uninstall_plugin"]
    args: UninstallPluginArgs


# ---------------------------------------------------------------------------
# update_setting — change a non-credential system setting.
# Credential-bearing settings (AI providers, MQTT) are excluded.
# ---------------------------------------------------------------------------

SettingCategory = Literal[
    "display",
    "transitions",
    "output",
    "polling",
    "location",
    "silence_schedule",
    "active_page",
]


class UpdateSettingArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: SettingCategory
    values: dict[str, Any] = Field(default_factory=dict)


class UpdateSettingOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["update_setting"]
    args: UpdateSettingArgs


# ---------------------------------------------------------------------------
# create_carousel / update_carousel — manage page carousels.
# ---------------------------------------------------------------------------


class CreateCarouselArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=100)
    page_ids: list[str] = Field(default_factory=list)
    interval_seconds: int = Field(30, ge=5, le=3600)


class CreateCarouselOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["create_carousel"]
    args: CreateCarouselArgs


class UpdateCarouselArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    carousel_id: str = Field(..., description="ID of the carousel to update.")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    page_ids: list[str] | None = None
    interval_seconds: int | None = Field(default=None, ge=5, le=3600)


class UpdateCarouselOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["update_carousel"]
    args: UpdateCarouselArgs


# ---------------------------------------------------------------------------
# create_schedule / update_schedule / delete_schedule — manage the
# display schedule (which page shows at what time).
# ---------------------------------------------------------------------------

DayPattern = Literal["all", "weekdays", "weekends", "custom"]
_VALID_CUSTOM_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


class CreateScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_id: str = Field(..., description="Page or carousel ID to show.")
    start_time: str = Field(..., description="24h HH:MM start time.")
    end_time: str | None = Field(default=None, description="24h HH:MM end time, or null for open-ended.")
    day_pattern: DayPattern = "all"
    custom_days: list[str] | None = Field(default=None, description="Required when day_pattern='custom'.")
    enabled: bool = True


class CreateScheduleOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["create_schedule"]
    args: CreateScheduleArgs


class UpdateScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schedule_id: str = Field(..., description="ID of the schedule entry to update.")
    page_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    day_pattern: DayPattern | None = None
    custom_days: list[str] | None = None
    enabled: bool | None = None


class UpdateScheduleOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["update_schedule"]
    args: UpdateScheduleArgs


class DeleteScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schedule_id: str = Field(..., description="ID of the schedule entry to delete.")


class DeleteScheduleOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["delete_schedule"]
    args: DeleteScheduleArgs


# ---------------------------------------------------------------------------
# update_plugin — trigger a registry update for an installed plugin.
# ---------------------------------------------------------------------------


class UpdatePluginArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugin_id: str = Field(..., min_length=1, max_length=100)


class UpdatePluginOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["update_plugin"]
    args: UpdatePluginArgs


# ---------------------------------------------------------------------------
# navigate_to_schedule — open the schedule editor, optionally pre-filling a
# new entry form.
# ---------------------------------------------------------------------------


class NavigateToScheduleArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prefill: dict[str, Any] | None = Field(default=None)


class NavigateToScheduleOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["navigate_to_schedule"]
    args: NavigateToScheduleArgs


# ---------------------------------------------------------------------------
# trigger_system_update — trigger a FiestaBoard system update.
# ---------------------------------------------------------------------------


class TriggerSystemUpdateArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TriggerSystemUpdateOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["trigger_system_update"]
    args: TriggerSystemUpdateArgs


# ---------------------------------------------------------------------------
# update_task_list — frontend-only task tracker (no API call).
# The model emits this to announce and update a running todo list so the
# user can see progress across multi-step autonomous sessions.
# ---------------------------------------------------------------------------

TaskStatus = Literal["pending", "in_progress", "done", "failed"]


class TaskItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=200)
    status: TaskStatus = "pending"


class UpdateTaskListArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tasks: list[TaskItem] = Field(default_factory=list)


class UpdateTaskListOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: Literal["update_task_list"]
    args: UpdateTaskListArgs


# ---------------------------------------------------------------------------
# Discriminated union + helper.
# ---------------------------------------------------------------------------


ToolCall = Union[  # noqa: UP007 — pydantic discriminated-union requires typing.Union
    ReplacePageOp,
    ApplyPatchOp,
    SuggestVariablesOp,
    NavigateToPageOp,
    NavigateToScheduleOp,
    InstallPluginOp,
    UpdatePluginConfigOp,
    EnablePluginOp,
    DisablePluginOp,
    UninstallPluginOp,
    UpdateSettingOp,
    CreateCarouselOp,
    UpdateCarouselOp,
    CreateScheduleOp,
    UpdateScheduleOp,
    DeleteScheduleOp,
    UpdatePluginOp,
    TriggerSystemUpdateOp,
    UpdateTaskListOp,
]


_OP_REGISTRY = {
    "replace_page": ReplacePageOp,
    "apply_patch": ApplyPatchOp,
    "suggest_variables": SuggestVariablesOp,
    "navigate_to_page": NavigateToPageOp,
    "navigate_to_schedule": NavigateToScheduleOp,
    "install_plugin": InstallPluginOp,
    "update_plugin_config": UpdatePluginConfigOp,
    "enable_plugin": EnablePluginOp,
    "disable_plugin": DisablePluginOp,
    "uninstall_plugin": UninstallPluginOp,
    "update_setting": UpdateSettingOp,
    "create_carousel": CreateCarouselOp,
    "update_carousel": UpdateCarouselOp,
    "create_schedule": CreateScheduleOp,
    "update_schedule": UpdateScheduleOp,
    "delete_schedule": DeleteScheduleOp,
    "update_plugin": UpdatePluginOp,
    "trigger_system_update": TriggerSystemUpdateOp,
    "update_task_list": UpdateTaskListOp,
}


class ToolCallValidationError(ValueError):
    """Raised when a fenced block fails schema validation."""


def parse_tool_call(payload: object) -> ToolCall:
    """Validate a parsed JSON object against the operation grammar.

    The model is asked to emit ``{"op": "...", "args": {...}}``. We
    dispatch on ``op`` and validate against the corresponding model so
    Pydantic gives us per-field errors (better UX than a giant union
    failure).
    """
    if not isinstance(payload, dict):
        raise ToolCallValidationError("Tool call must be a JSON object.")
    op = payload.get("op")
    if not isinstance(op, str):
        raise ToolCallValidationError(
            "Tool call is missing the required 'op' string."
        )
    model_cls = _OP_REGISTRY.get(op)
    if model_cls is None:
        raise ToolCallValidationError(f"Unknown tool op: {op!r}")
    try:
        return model_cls.model_validate(payload)
    except Exception as exc:  # pydantic.ValidationError, etc.
        raise ToolCallValidationError(str(exc)) from exc


def supported_ops() -> list[str]:
    """Stable list of supported op names — used in the system prompt."""
    return list(_OP_REGISTRY.keys())
