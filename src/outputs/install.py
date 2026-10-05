"""Outputs the user can pick before they are installed (plan D18).

The setup wizard's first step asks what FiestaBoard should show on, and
offers every output this install could drive — not only the installed ones:

- :func:`list_available_outputs` (``GET /outputs/available``): the installed
  outputs (:func:`~src.outputs.actions.list_outputs`: built-ins first), then
  the seed's **loadable** first-party outputs (:mod:`src.outputs.seed`; they
  install with no network), then plugin-registry entries whose
  ``plugin_type`` is ``output``. Each id once, in that precedence. The
  registry is read best-effort: when it cannot be read the list is the
  installed and seeded outputs, never an error.
- :func:`install_output` (``POST /outputs/{output_id}/install``): installs
  the chosen output from the seed (offline) or, failing that, from the
  registry through the normal install path — which is where the
  ``output_api`` gate refuses a plugin this core cannot run (plan D8).
  Idempotent: an installed output is answered as it is. Seeded outputs are
  first-party and install with the beta off; a registry (third-party)
  output is beta-gated (``beta.output_plugins_enabled``), checked before
  anything is fetched. The loader draws the same line.

Raises domain errors; ``routes.py`` maps them.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.plugins import sources

from .actions import describe_output, list_outputs
from .errors import (
    OutputInstallRefusedError,
    OutputNotInstallableError,
    OutputPluginsDisabledError,
    OutputSourceUnreachableError,
)
from .plugin_registration import output_plugins_enabled
from .registry import output_registry
from .seed import seed_root, seeded_entries, seeded_output

logger = logging.getLogger(__name__)

#: How ``clone_or_update_repo`` reports a fetch that never reached the repository.
_FETCH_FAILURES = ("git clone failed", "git fetch/reset failed")


def _plugin_registry():
    from src.plugins.registry import get_plugin_registry

    return get_plugin_registry()


def _registry_outputs() -> list[sources.RegistryEntry]:
    """The plugin registry's output entries; none when it cannot be read."""
    try:
        return [entry for entry in sources.load_registry() if entry.plugin_type == "output"]
    except Exception as exc:
        logger.warning("The plugin registry could not be read; listing installed and seeded outputs only: %s", exc)
        return []


def _seeded_manifest(plugin_id: str) -> dict[str, Any] | None:
    copy = seeded_output(plugin_id)
    if copy is None:
        return None
    try:
        manifest = json.loads((copy.path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("The seed's copy of output '%s' has an unreadable manifest: %s", plugin_id, exc)
        return None
    return manifest if isinstance(manifest, dict) else None


def list_available_outputs() -> list[dict[str, Any]]:
    """Installed outputs, then seeded, then registry outputs; each id once."""
    listed: list[dict[str, Any]] = [
        {
            "id": output["id"],
            "name": output["name"],
            "description": output["description"],
            "icon": output["icon"],
            "source": "installed",
            "installed": True,
            "builtin": output["builtin"],
            "beta_gated": output["beta_gated"],
            "available": output["available"],
            "needs_network": False,
            "output_api": output["output_api"],
        }
        for output in list_outputs()
    ]
    seen = {entry["id"] for entry in listed}
    beta = output_plugins_enabled()

    seeded: list[dict[str, Any]] = []
    for plugin_id, entry in seeded_entries(seed_root()).items():
        if plugin_id in seen:
            continue
        manifest = _seeded_manifest(plugin_id)  # None for a data-only entry: never loaded, never offered
        if manifest is None:
            continue
        seeded.append(
            {
                "id": plugin_id,
                "name": str(manifest.get("name") or plugin_id),
                "description": str(manifest.get("description") or ""),
                "icon": manifest.get("icon") if isinstance(manifest.get("icon"), str) else None,
                "source": "seed",
                "installed": False,
                "builtin": False,
                "beta_gated": False,
                "available": True,
                "needs_network": False,
                "output_api": entry.output_api,
            }
        )
    seeded.sort(key=lambda e: e["name"].lower())
    listed += seeded
    seen |= {entry["id"] for entry in seeded}

    for entry in sorted(_registry_outputs(), key=lambda e: e.name.lower()):
        if entry.plugin_id in seen:
            continue
        seen.add(entry.plugin_id)
        listed.append(
            {
                "id": entry.plugin_id,
                "name": entry.name or entry.plugin_id,
                "description": entry.description,
                "icon": entry.icon or None,
                "source": "registry",
                "installed": False,
                "builtin": False,
                "beta_gated": True,
                "available": beta,
                "needs_network": True,
                "output_api": None,
            }
        )
    return listed


def install_output(output_id: str) -> tuple[dict[str, Any], bool]:
    """Install output *output_id*; ``(its GET /outputs entry, newly installed)``.

    Raises:
        OutputNotInstallableError: nothing offers it.
        OutputPluginsDisabledError: it is third-party and the beta is off.
        OutputInstallRefusedError: it was fetched but cannot run here.
        OutputSourceUnreachableError: its repository could not be fetched.
    """
    definition = output_registry().get(output_id)
    if definition is not None:
        if definition.beta_gated and not output_plugins_enabled():
            raise OutputPluginsDisabledError(output_id)
        return describe_output(definition), False

    from_seed = seeded_output(output_id) is not None
    if not from_seed and not any(entry.plugin_id == output_id for entry in _registry_outputs()):
        raise OutputNotInstallableError(output_id)
    if not from_seed and not output_plugins_enabled():
        raise OutputPluginsDisabledError(output_id)

    registry = _plugin_registry()
    errors = registry.install_output_from_seed(output_id) if from_seed else registry.install_from_registry(output_id)
    if errors:
        reason = "; ".join(errors)
        logger.error("Output %s was not installed: %s", output_id, reason)
        if not from_seed and any(e.startswith(_FETCH_FAILURES) for e in errors):
            raise OutputSourceUnreachableError(f"Could not download '{output_id}': {reason}")
        raise OutputInstallRefusedError(reason)

    definition = output_registry().get(output_id)
    if definition is None:
        raise OutputInstallRefusedError(f"'{output_id}' was installed but is not an output plugin.")
    logger.info("Installed output %s from the %s", output_id, "seed" if from_seed else "plugin registry")
    return describe_output(definition), True
