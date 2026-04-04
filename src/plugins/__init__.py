"""Plugin system for FiestaBoard.

This module provides a plugin-based architecture for data source integrations.
Each plugin is self-contained with its own manifest, code, and documentation.

Plugins can be loaded from three sources:

1. **Built-in** – shipped in the ``plugins/`` directory of this repository.
2. **Registry** – listed in ``plugin-registry.json`` and cloned from git
   repositories that follow the ``fiestaboard-plugin--{name}`` naming
   convention.
3. **Git URL** – arbitrary public git repositories specified by the user.
"""

from .base import PluginBase, PluginResult, TriggerResult
from .registry import PluginRegistry, get_plugin_registry
from .loader import PluginLoader
from .manifest import PluginManifest, validate_manifest
from .sources import (
    PluginSource,
    RegistryEntry,
    load_registry,
    validate_registry_repo_name,
    plugin_id_from_repo_name,
)

__all__ = [
    "PluginBase",
    "PluginResult",
    "TriggerResult",
    "PluginRegistry",
    "get_plugin_registry",
    "PluginLoader",
    "PluginManifest",
    "validate_manifest",
    "PluginSource",
    "RegistryEntry",
    "load_registry",
    "validate_registry_repo_name",
    "plugin_id_from_repo_name",
]

# Testing utilities (imported separately to avoid test dependencies in production)
# Usage: from src.plugins.testing import PluginTestCase

