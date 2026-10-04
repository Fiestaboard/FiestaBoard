"""Plugin system for FiestaBoard.

This module provides a plugin-based architecture for data source integrations.
Each plugin is self-contained with its own manifest, code, and documentation.

Plugins can be loaded from three sources:

Three kinds: **data** plugins (template variables), **transition** plugins
(frame-by-frame animations) and **output** plugins (a display device, one
instance per board -- :class:`OutputPluginBase`, see :mod:`src.outputs`).

1. **Built-in** – shipped in the ``plugins/`` directory of this repository.
2. **Registry** – listed in ``plugin-registry.json`` and cloned from git
   repositories that follow the ``fiestaboard-plugin--{name}`` naming
   convention.
3. **Git URL** – arbitrary public git repositories specified by the user.

**The output-plugin author API** is importable from here, so an output
plugin depends on one module: the contract (:class:`OutputPluginBase`,
:class:`WriteResult`, :class:`CancelToken`, :data:`CellFrame`,
:data:`RichCellFrame`...), the device helper's types (:class:`OutputHttp`,
:class:`RequestCancelled`, :class:`OutputHostBlocked`), the rich cell
(:class:`BoardToken`, :func:`cells_from_codes`, :func:`characters_to_message`)
and core's LED renderer (:mod:`src.led`: :func:`layout_message`,
:func:`rasterize`, :func:`plan_transition`, :func:`transition_frames`,
:func:`resolve_led_transition`, :func:`led_flip_seed`...). Versioned with
the manifest's ``output_api``.
"""

from src.board_chars import characters_to_message
from src.led import (
    LedLayout,
    LedLayoutOptions,
    LedMatrixSpec,
    LedTransitionSpec,
    ResolvedLedTransition,
    layout_message,
    led_flip_seed,
    led_spec_for_model,
    plan_transition,
    rasterize,
    resolve_led_transition,
    transition_frames,
)
from src.markup import BoardToken
from src.output_allowlist import OutputHostBlocked
from src.outputs.author_kit import (
    check_dns_resolution,
    check_output_host,
    check_port_reachable,
    describe_request_error,
    local_ipv4,
    text_to_board_array,
    unconfigured_board_section,
    validate_board_host,
    validate_board_host_is_local_network,
)
from src.outputs.cells import cells_from_codes
from src.outputs.hooks import OutputActionError, ReadBack
from src.outputs.http import OutputHttp, RequestCancelled
from src.outputs.plugin_base import (
    ActionField,
    ActionOutcome,
    CancelToken,
    CellFrame,
    ConnectionCheck,
    DiagnosticCheck,
    FrameRegion,
    OutputPluginBase,
    RichCellFrame,
    TimedFrame,
    WriteResult,
)

from .base import (
    PluginBase,
    PluginResult,
    TransitionFrame,
    TransitionPluginBase,
    TriggerResult,
)
from .loader import PluginLoader
from .manifest import DemoPageSchema, PluginManifest, validate_manifest
from .registry import INSTANCE_SEPARATOR, PluginRegistry, get_plugin_registry
from .sources import (
    PluginSource,
    RegistryEntry,
    load_registry,
    plugin_id_from_repo_name,
    validate_registry_repo_name,
)

__all__ = [
    "INSTANCE_SEPARATOR",
    "ActionField",
    "ActionOutcome",
    "BoardToken",
    "CancelToken",
    "CellFrame",
    "ConnectionCheck",
    "DemoPageSchema",
    "DiagnosticCheck",
    "FrameRegion",
    "LedLayout",
    "LedLayoutOptions",
    "LedMatrixSpec",
    "LedTransitionSpec",
    "OutputActionError",
    "OutputHostBlocked",
    "OutputHttp",
    "OutputPluginBase",
    "PluginBase",
    "PluginLoader",
    "PluginManifest",
    "PluginRegistry",
    "PluginResult",
    "PluginSource",
    "ReadBack",
    "RegistryEntry",
    "RequestCancelled",
    "ResolvedLedTransition",
    "RichCellFrame",
    "TimedFrame",
    "TransitionFrame",
    "TransitionPluginBase",
    "TriggerResult",
    "WriteResult",
    "cells_from_codes",
    "characters_to_message",
    "check_dns_resolution",
    "check_output_host",
    "check_port_reachable",
    "describe_request_error",
    "get_plugin_registry",
    "layout_message",
    "led_flip_seed",
    "led_spec_for_model",
    "load_registry",
    "local_ipv4",
    "plan_transition",
    "plugin_id_from_repo_name",
    "rasterize",
    "resolve_led_transition",
    "text_to_board_array",
    "transition_frames",
    "unconfigured_board_section",
    "validate_board_host",
    "validate_board_host_is_local_network",
    "validate_manifest",
    "validate_registry_repo_name",
]

# Testing utilities (imported separately to avoid test dependencies in production)
# Usage: from src.plugins.testing import PluginTestCase
