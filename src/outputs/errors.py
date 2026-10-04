"""The outputs domain's errors. No HTTP status lives here: ``routes.py`` maps
each to its code (API_CONVENTIONS.md, "Routers and services")."""

from __future__ import annotations

from .geometry import BelowFloorError, GeometryError
from .plugin_registration import OutputPluginsDisabledError

__all__ = [
    "BelowFloorError",
    "BoardNotFoundError",
    "BuiltinOutputError",
    "GeometryError",
    "InvalidActionInputError",
    "InvalidOutputConfigError",
    "OutputInstallRefusedError",
    "OutputNotInstallableError",
    "OutputNotInstalledError",
    "OutputPluginsDisabledError",
    "OutputSourceUnreachableError",
    "UndeclaredDeviceModelError",
]


class OutputNotInstalledError(LookupError):
    """No output plugin is installed under this id."""

    def __init__(self, output_id: str) -> None:
        super().__init__(f"Output '{output_id}' is not installed.")


class BuiltinOutputError(ValueError):
    """The built-in outputs are created through their own routes."""

    def __init__(self, output_id: str) -> None:
        super().__init__(
            f"'{output_id}' boards are not created here: add a Vestaboard with POST /settings/board/add "
            "and a FiestaPanel with POST /panels."
        )


class UndeclaredDeviceModelError(ValueError):
    """The output plugin does not declare the requested device model."""

    def __init__(self, output_id: str, model_id: str, declared: tuple[str, ...]) -> None:
        super().__init__(
            f"Output '{output_id}' declares no device model '{model_id}'. It declares: {', '.join(declared)}."
        )


class InvalidOutputConfigError(ValueError):
    """The board's ``output_config`` does not fit the plugin's settings schema."""


class BoardNotFoundError(LookupError):
    """No saved board has this id."""

    def __init__(self, board_id: str) -> None:
        super().__init__(f"Board {board_id} not found")


class InvalidActionInputError(ValueError):
    """An action's ``input`` does not fit its declared ``input_schema``."""


class OutputNotInstallableError(LookupError):
    """Nothing offers an output under this id: not installed, not in the
    seed, not an output in the plugin registry."""

    def __init__(self, output_id: str) -> None:
        super().__init__(f"No installable output is named '{output_id}'.")


class OutputInstallRefusedError(ValueError):
    """The output was fetched but cannot run here (its output_api, its
    self-check) and was not installed."""


class OutputSourceUnreachableError(RuntimeError):
    """The output's repository could not be fetched (offline, host down)."""
