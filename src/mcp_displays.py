"""Generic display tools: declarations and actions belong to output plugins."""

from __future__ import annotations

from typing import Any


def register_display_tools(tool: Any, tool_error: type[Exception]) -> None:
    """Register through the server's standard annotation/error boundary."""
    from fastapi import HTTPException

    from .outputs.actions import describe_output
    from .outputs.registry import output_registry, resolve_output_id
    from .settings.service import get_settings_service

    def board_for(board_id: str | None) -> dict[str, Any]:
        settings = get_settings_service()
        target = board_id or settings.get_primary_board_id()
        board = next((b for b in settings.get_board_settings().boards or [] if b.get("id") == target), None)
        if board is None:
            raise tool_error(f"Board not found: {target}")
        return board

    @tool(read_only=True)
    def list_display_outputs(output_id: str | None = None) -> dict[str, Any]:
        """Discover installed display plugins, full models/charsets, settings schemas and actions.
        Filter by output_id for one declaration. Use get_display_info for a board's resolved capabilities.
        """
        from .outputs.actions import list_outputs

        if output_id is not None:
            definition = output_registry().get(output_id)
            if definition is None:
                raise tool_error(f"Output not installed: {output_id}")
            outputs = [describe_output(definition)]
        else:
            outputs = list_outputs()
        return {"description_version": 1, "outputs": outputs, "total": len(outputs)}

    @tool(read_only=True)
    def get_display_info(board_id: str | None = None) -> dict[str, Any]:
        """Describe a display's effective geometry, charset, canvas support, transport and masked settings.
        Omitted board_id selects the primary board. Uses declarations and existing runtime state;
        never opens a connection or probes hardware. Unavailable capabilities are null.
        """
        from .ops.executors import board_public_view
        from .outputs.config_hooks import mask_config

        board = board_for(board_id)
        output_id = resolve_output_id(board)
        definition = output_registry().get(output_id)
        return {
            **board_public_view(board),
            "output_config": mask_config(output_id, board.get("output_config") or {}),
            "output_description": describe_output(definition) if definition is not None else None,
        }

    @tool(destructive=False, idempotent=False)
    async def create_display(
        output_id: str,
        device_model: str,
        output_config: dict[str, Any],
        name: str | None = None,
        geometry: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Create a display from an installed plugin's declared model and settings schema.
        Discover declarations with list_display_outputs. Supply only user-provided credentials.
        Built-in Vestaboards use add_board; FiestaPanels use create_panel.
        """
        from .outputs.models import OutputBoardCreate
        from .outputs.routes import create_board

        try:
            result = await create_board(
                output_id,
                OutputBoardCreate(
                    device_model=device_model,
                    output_config=output_config,
                    name=name,
                    geometry=geometry,
                ),
            )
        except HTTPException as exc:
            raise tool_error(str(exc.detail)) from exc
        return {"status": "success", "board": result.model_dump(mode="json")}

    @tool(destructive=False, idempotent=True)
    async def configure_display(
        board_id: str,
        output_config: dict[str, Any],
        name: str | None = None,
        device_model: str | None = None,
    ) -> dict[str, Any]:
        """Merge a display's plugin settings; omitted keys retain their values and *** preserves secrets.
        Read get_display_info first for the schema and supported models. Font/layout edits use
        the output's normal configuration rules. Returns resize warnings. Never guess credentials.
        """
        from .ops.executors import board_public_view
        from .settings.models import BoardSettingsUpdate
        from .settings.routes import update_board_settings

        stored = board_for(board_id)
        definition = output_registry().get(resolve_output_id(stored))
        if definition is None:
            raise tool_error("The board's output is not installed.")
        if device_model is not None and device_model not in definition.offered_device_models:
            raise tool_error(f"Output does not declare device model: {device_model}")
        board = {**stored, "output_config": {**(stored.get("output_config") or {}), **output_config}}
        if name is not None:
            board["name"] = name
        if device_model is not None:
            board["device_model"] = device_model
        boards = [board if b.get("id") == board_id else b for b in get_settings_service().get_board_settings().boards]
        try:
            result = await update_board_settings(BoardSettingsUpdate(boards=boards))
        except HTTPException as exc:
            raise tool_error(str(exc.detail)) from exc
        saved = board_for(board_id)
        return {
            "status": "success",
            "board": board_public_view(saved),
            "retargeted_pages": result.get("retargeted_pages", []),
            "incompatible_references": result.get("incompatible_references", []),
        }

    @tool(destructive=True, idempotent=False, open_world=True)
    async def run_display_action(
        board_id: str,
        action: str,
        inputs: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a declared action on a saved display with its selected model and geometry.
        Read get_display_info for action schemas/effects first. May contact or change hardware;
        only invoke the action the user requested. Optional edited settings are not persisted.
        Secret result values are masked. Device refusals remain errors.
        """
        from .outputs.models import SavedBoardActionRequest
        from .outputs.routes import run_board_action

        try:
            result = await run_board_action(
                board_id, action, SavedBoardActionRequest(input=inputs or {}, output_config=output_config)
            )
        except HTTPException as exc:
            raise tool_error(str(exc.detail)) from exc
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
        for field in (payload.get("fields") or {}).values():
            if field.get("secret"):
                field["value"] = "***"
        if payload.get("status") == "error":
            payload["error"] = payload.get("message") or "The display action failed."
        return payload
