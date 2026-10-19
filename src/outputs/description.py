"""Safe, resolved display metadata shared by assistant-facing board views."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any


def describe_board(board: dict[str, Any]) -> dict[str, Any]:
    """Describe declared capabilities without opening a connection to a device.

    Effective runtime capabilities replace declarations only when a live
    driver already exists. Configuration and credentials are never returned.
    """
    from src.devices import dimensions_of

    from .actions import describe_output
    from .board_profile import board_character_set, board_device_model, board_model_spec, board_profile
    from .config_hooks import board_status, mask_config
    from .display_profile import display_profile_for_board
    from .registry import FIRST_PARTY_OUTPUTS, output_registry, resolve_output_id

    output_id = resolve_output_id(board)
    definition = output_registry().get(output_id)
    declaration = describe_output(definition) if definition is not None else None
    dims = dimensions_of(board)
    profile = display_profile_for_board(board) if definition is not None else None
    model = board_device_model(board) if definition is not None else None
    charset = (
        profile.character_set
        if profile is not None
        else (board_character_set(board) if definition is not None else None)
    )
    if definition is not None and output_id in FIRST_PARTY_OUTPUTS:
        from src.fiestaui import builtin_device_models

        # board_device_model intentionally describes plugin boards only.
        # Legacy boards resolve through their existing shape/style helpers;
        # an arbitrary missing plugin must never fall back to this catalog.
        model = board_model_spec(board) or builtin_device_models().get(board_profile(board).device_model)
    status = board_status(board)
    config = board.get("output_config") or {}
    masked = mask_config(output_id, config)

    def has_secret(value: Any) -> bool:
        if isinstance(value, dict):
            return any(has_secret(v) for v in value.values())
        if isinstance(value, list):
            return any(has_secret(v) for v in value)
        return value == "***"

    capabilities = definition.capabilities if definition is not None else None
    capability_source = "output_declaration" if capabilities is not None else "unavailable"
    # A read endpoint must not initialize a device or a display service.
    from src.api_server import peek_service

    engine = peek_service()
    get_client = getattr(engine, "get_board_client", None)
    if callable(get_client):
        client = get_client(board.get("id"))
        actual = getattr(client, "capabilities", None)
        from .registry import OutputCapabilities

        if isinstance(actual, OutputCapabilities):
            capabilities = actual
            capability_source = "runtime"
    caps = asdict(capabilities) if capabilities is not None else None
    if caps is not None:
        caps["native_transitions"] = sorted(capabilities.native_transitions)
        caps["device_models"] = list(capabilities.device_models)
    return {
        "description_version": 1,
        "output": output_id,
        "output_api": declaration["output_api"] if declaration is not None else None,
        "output_version": declaration["version"] if declaration is not None else None,
        "declaration_revision": declaration["declaration_revision"] if declaration is not None else None,
        "device_model": model.get("id") if model is not None else board.get("device_model"),
        "device_model_document": dict(model) if model is not None else None,
        "charset": charset.get("id") if charset is not None else None,
        "rows": dims.rows,
        "cols": dims.cols,
        "grid_rows": board.get("grid_rows"),
        "grid_cols": board.get("grid_cols"),
        "geometry_source": "configured",
        "display": profile.to_dict() if profile is not None else None,
        "capabilities": caps,
        "capability_source": capability_source,
        "configuration_status": asdict(status) if status is not None else None,
        "observation": {
            "availability": "not_probed" if definition is not None else "unavailable",
            "source": None,
            "observed_at": None,
        },
        "has_host": bool(config.get("host")) if isinstance(config, dict) else False,
        "has_credentials": has_secret(masked),
    }


def mask_output_settings(value: Any) -> Any:
    """Apply each output's secret policy to board records inside a settings tree."""
    from .config_hooks import mask_config
    from .registry import resolve_output_id

    if isinstance(value, list):
        return [mask_output_settings(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: mask_output_settings(item) for key, item in value.items() if key != "output_config"}
    if "output_config" in value:
        result["output_config"] = mask_config(resolve_output_id(value), value["output_config"])
    return result
