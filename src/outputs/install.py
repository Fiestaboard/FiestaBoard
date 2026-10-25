"""Outputs the user can pick before they are installed (plan D18).

The setup wizard's first step asks what FiestaBoard should show on, and the
Displays page's marketplace lists what FiestaBoard can drive; both offer
every output this install could drive — not only the installed ones:

- :func:`list_available_outputs` (``GET /outputs/available``): the installed
  outputs (:func:`~src.outputs.actions.list_outputs`: built-ins first), then
  the seed's **loadable** outputs (:mod:`src.outputs.seed`; they
  install with no network), then plugin-registry entries whose
  ``plugin_type`` is ``output``. Each id once, in that precedence. The
  registry is read best-effort: when it cannot be read the list is the
  installed and seeded outputs, never an error.
- :func:`install_output` (``POST /outputs/{output_id}/install``): installs
  the chosen output from the seed (offline) or, failing that, from the
  registry through the normal install path — which is where the
  ``output_api`` gate refuses a plugin this core cannot run (plan D8).
  Idempotent: an installed output is answered as it is. No opt-in gates
  any of them (settings v7 dropped ``plugins.output_plugins_enabled``).

Raises domain errors; ``routes.py`` maps them.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.plugins import sources

from .actions import describe_output, list_outputs
from .catalog_metadata import display_metadata
from .errors import (
    OutputInstallRefusedError,
    OutputNotInstallableError,
    OutputSourceUnreachableError,
)
from .output_manifest import parse_output_block
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
    """Legacy array API; the catalog also reports incomplete discovery."""
    return list_output_catalog()["outputs"]


def list_output_catalog() -> dict[str, Any]:
    """Local outputs remain usable when marketplace discovery fails."""
    try:
        entries = [entry for entry in sources.load_registry(strict=True) if entry.plugin_type == "output"]
        registry_status = "available"
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Display catalog unavailable: %s", exc)
        entries = []
        registry_status = "unavailable"
    registry_by_id = {entry.plugin_id: entry for entry in entries}
    local_metadata: dict[str, dict[str, Any]] = {}
    fallback_categories: dict[str, str] = {}
    installed = list_outputs()
    for output in installed:
        manifest = _plugin_registry().get_manifest(output["id"])
        raw = manifest.raw.get("display") if manifest else None
        meta = display_metadata(raw)
        meta["models"] = list(dict.fromkeys([*meta["models"], *(m["label"] for m in output["device_models"])]))
        local_metadata[output["id"]] = meta
        technology = output["capabilities"]["technology"]
        fallback_categories[output["id"]] = (
            "TV & browser"
            if output["id"] == "fiestapanel"
            else {"split_flap": "Split-flap displays", "led_matrix": "LED displays"}.get(technology, "")
        )
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
        for output in installed
    ]
    seen = {entry["id"] for entry in listed}

    seeded: list[dict[str, Any]] = []
    for plugin_id, entry in seeded_entries(seed_root()).items():
        if plugin_id in seen:
            continue
        manifest = _seeded_manifest(plugin_id)  # None for a data-only entry: never loaded, never offered
        if manifest is None:
            continue
        meta = display_metadata(manifest.get("display"))
        copy = seeded_output(plugin_id)
        parsed, _ = parse_output_block(
            manifest.get("output"), base_dir=copy.path if copy else None, data_files=manifest.get("data_files", [])
        )
        if parsed is not None:
            models = [parsed.model(index) for index in range(len(parsed.device_models))]
            meta["models"] = list(dict.fromkeys([*meta["models"], *(model["label"] for model in models)]))
            technologies = {model["technology"] for model in models}
            if len(technologies) == 1:
                fallback_categories[plugin_id] = {
                    "split_flap": "Split-flap displays",
                    "led_matrix": "LED displays",
                }.get(next(iter(technologies)), "")
        local_metadata[plugin_id] = meta
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

    for entry in sorted(entries, key=lambda e: e.name.lower()):
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
                "beta_gated": False,
                "available": True,
                "needs_network": True,
                "output_api": None,
            }
        )
    for output in listed:
        entry = registry_by_id.get(output["id"])
        remote = display_metadata(entry.display if entry else None)
        local = local_metadata.get(output["id"], display_metadata(None))
        output["display"] = {
            "category": local["category"] or remote["category"] or fallback_categories.get(output["id"], ""),
            "manufacturer": local["manufacturer"] or remote["manufacturer"],
            "models": list(dict.fromkeys([*local["models"], *remote["models"]])),
            "keywords": list(dict.fromkeys([*local["keywords"], *remote["keywords"]])),
        }
    return {"outputs": listed, "registry_status": registry_status}


def install_output(output_id: str) -> tuple[dict[str, Any], bool]:
    """Install output *output_id*; ``(its GET /outputs entry, newly installed)``.

    Raises:
        OutputNotInstallableError: nothing offers it.
        OutputInstallRefusedError: it was fetched but cannot run here.
        OutputSourceUnreachableError: its repository could not be fetched.
    """
    definition = output_registry().get(output_id)
    if definition is not None:
        return describe_output(definition), False

    # The first request after startup can initialize the plugin registry,
    # registering outputs already on disk. Check again before offering or
    # copying anything, including installed outputs no longer in a catalog.
    registry = _plugin_registry()
    definition = output_registry().get(output_id)
    if definition is not None:
        return describe_output(definition), False

    from_seed = seeded_output(output_id) is not None
    if not from_seed and not any(entry.plugin_id == output_id for entry in _registry_outputs()):
        raise OutputNotInstallableError(output_id)

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
