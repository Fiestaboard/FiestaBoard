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
"""

from src.outputs.plugin_base import (
    CancelToken,
    CellFrame,
    ConnectionCheck,
    DiagnosticCheck,
    FrameRegion,
    OutputPluginBase,
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
    "CancelToken",
    "CellFrame",
    "ConnectionCheck",
    "DemoPageSchema",
    "DiagnosticCheck",
    "FrameRegion",
    "OutputPluginBase",
    "PluginBase",
    "PluginLoader",
    "PluginManifest",
    "PluginRegistry",
    "PluginResult",
    "PluginSource",
    "RegistryEntry",
    "TimedFrame",
    "TransitionFrame",
    "TransitionPluginBase",
    "TriggerResult",
    "WriteResult",
    "get_plugin_registry",
    "load_registry",
    "plugin_id_from_repo_name",
    "validate_manifest",
    "validate_registry_repo_name",
]

# Testing utilities (imported separately to avoid test dependencies in production)
# Usage: from src.plugins.testing import PluginTestCase
