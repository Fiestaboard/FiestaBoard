"""The first-party outputs — Vestaboard and FiestaPanel — loaded from the output seed.

Phase 4 of the output-plugins program turned the two devices FiestaBoard was
built for into output plugins like any other, each in its own repository
(``Fiestaboard/fiestaboard-output--vestaboard`` / ``--fiestapanel``). The
image carries them in the **output seed** (:mod:`src.outputs.seed`) at the
commits ``outputs.lock.json`` pins, and this module loads each one from
there through the output-plugin path — its manifest validated by
:func:`src.plugins.manifest.load_manifest` (``$ref`` device models
included), its ``OutputPluginBase`` subclass imported as ``plugins.<id>``
(the name the plugin loader gives any output plugin, and the one the
package's own tests import it by) — and puts it in the output registry under
its id, ``vestaboard`` / ``fiestapanel``. Offline by construction: the seed
was fetched at image build.

**Trust.** Only an id in :data:`FIRST_PARTY_OUTPUTS` **and** pinned as
loadable in the seed's lock loads here, and only a seed copy whose tree
digest matches the lock's ``tree_sha256`` (checked at every load, so a
corrupted or hand-edited copy is refused, never run). An id the lock does not
list is not first-party: nothing is loaded for it and its boards stay down
with the reason logged. Updates arrive as a bumped pin in core's lockfile:
the image build verifies the commit, digest and ``output_api`` (the seed
build), and this load verifies digest and ``output_api`` again; rolling back
is rolling back the image. There is no in-app update path for them, and an
installed plugin can never stand in for one (:func:`is_first_party_output`;
the plugin loader refuses such a copy before importing it, and the seed
never installs them as plugins).

**Contributors** point an output at a local checkout of its repository with
``FIESTABOARD_DEV_OUTPUT_<ID>`` (``FIESTABOARD_DEV_OUTPUT_VESTABOARD=/path``):
that copy loads instead of the seed's, without the digest check, with a
warning in the log (``docs/internal/development/FIRST_PARTY_OUTPUTS.md``).

They differ from a third-party output plugin in four ways, each on purpose:

- **Never beta-gated**, and **never replaced**: the registry entry is
  ``plugin=False``, so an installed plugin cannot take the id.
- **Their boards predate** ``output_config``: each instance is built from
  the board by the plugin's own ``config_from_board`` (today's flat fields;
  ``None`` → no usable connection, no driver). Settings v4 (P4c) moves the
  fields; nothing on disk changes here.
- **They behave exactly as before** (``tests/golden/wire``): the driver runs
  their writes inline with no budget or breaker (``first_party=True``) and
  their requests are the ``requests`` module calls they always were
  (:meth:`OutputHttp.for_first_party <src.outputs.http.OutputHttp.for_first_party>`).
- **They present as they always have**: ``GET /outputs`` shows no
  ``output_api``, no settings schema (their settings screens are still the
  hand-coded ones until P4d) and FiestaPanel's ``vestaboard_panel`` model;
  board-settings actions still run through core's legacy dispatchers, which
  call into the plugin for every device conversation.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Literal

from .hooks import ActionCall, ActionOutcome, OutputDiagnostics, OutputHooks
from .plugin_base import OutputPluginBase
from .registry import FIESTAPANEL, FIRST_PARTY_OUTPUTS, VESTABOARD, OutputDefinition, OutputRegistry
from .seed import LOCKFILE, LockError, seed_root, seeded_entries, tree_digest

if TYPE_CHECKING:
    from src.plugins.manifest import PluginManifest

    from .driver import OutputDriver

logger = logging.getLogger(__name__)

__all__ = [
    "DEV_OUTPUT_ENV_PREFIX",
    "FIRST_PARTY_OUTPUTS",
    "FirstPartyOutput",
    "FirstPartyOutputError",
    "FirstPartySource",
    "first_party_definition",
    "first_party_module",
    "first_party_source",
    "import_first_party_package",
    "is_first_party_output",
    "load_first_party",
    "register_first_party_outputs",
]

#: The package namespace a first-party output is imported under.
MODULE_PREFIX = "plugins"
#: ``FIESTABOARD_DEV_OUTPUT_<ID>``: load that output from a local checkout.
DEV_OUTPUT_ENV_PREFIX = "FIESTABOARD_DEV_OUTPUT_"

#: Device models the "add a board" cards offer for an output, where that
#: still differs from its manifest (until settings v4 / P4d).
_LEGACY_OFFERED_MODELS: dict[str, tuple[str, ...]] = {FIESTAPANEL: ("vestaboard_panel",)}


class FirstPartyOutputError(RuntimeError):
    """A first-party output could not be loaded (not seeded, refused, invalid)."""


def is_first_party_output(output_id: object) -> bool:
    """Whether *output_id* is one of the outputs core itself loads from the seed."""
    return output_id in FIRST_PARTY_OUTPUTS


@dataclass(frozen=True)
class FirstPartySource:
    """Where a first-party output's package is loaded from."""

    output_id: str
    path: Path
    #: ``seed`` (digest-verified against the lock) or ``dev`` (an override).
    origin: Literal["seed", "dev"]
    #: The pinned commit (``None`` for a dev override).
    commit: str | None
    #: The ``output_api`` the lock pins (``None`` for a dev override).
    output_api: int | None = None


@dataclass(frozen=True)
class FirstPartyOutput:
    """A loaded first-party output: its plugin class, parsed manifest and source."""

    plugin_class: type[OutputPluginBase]
    manifest: PluginManifest
    source: FirstPartySource


def dev_override_env(output_id: str) -> str:
    """The environment variable that points *output_id* at a local checkout."""
    return f"{DEV_OUTPUT_ENV_PREFIX}{output_id.upper()}"


def first_party_source(output_id: str, seed_dir: Path | None = None) -> FirstPartySource:
    """Find first-party output *output_id*: a dev override, else the seed.

    Raises:
        FirstPartyOutputError: *output_id* is not first-party; the override
            names no package; the seed's lock does not pin it as loadable;
            or the seed's copy does not match the lock's ``tree_sha256``.
    """
    if not is_first_party_output(output_id):
        raise FirstPartyOutputError(f"'{output_id}' is not a first-party output")
    override = os.environ.get(dev_override_env(output_id), "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        if not (path / "manifest.json").is_file():
            raise FirstPartyOutputError(f"{output_id}: {dev_override_env(output_id)}={override} holds no manifest.json")
        logger.warning(
            "First-party output %s is loaded from a local checkout (%s=%s), not the seed",
            output_id,
            dev_override_env(output_id),
            path,
        )
        return FirstPartySource(output_id, path, "dev", None)

    root = Path(seed_dir) if seed_dir is not None else seed_root()
    entry = seeded_entries(root).get(output_id)
    if entry is None:
        raise FirstPartyOutputError(f"{output_id}: not pinned in the output seed's lock ({root / LOCKFILE})")
    if not entry.loadable:
        raise FirstPartyOutputError(f"{output_id}: the seed pins it as data only (loadable: false)")
    path = root / output_id
    try:
        digest = tree_digest(path)
    except LockError as exc:
        raise FirstPartyOutputError(f"{output_id}: the seed's copy is unusable: {exc}") from exc
    if digest != entry.tree_sha256:
        raise FirstPartyOutputError(
            f"{output_id}: the seed's copy has tree digest {digest}, the lock pins {entry.tree_sha256}; "
            "refusing to load it"
        )
    return FirstPartySource(output_id, path, "seed", entry.commit, entry.output_api)


def _evict(name: str) -> None:
    for module_name in [m for m in sys.modules if m == name or m.startswith(f"{name}.")]:
        del sys.modules[module_name]
    parent = sys.modules.get(MODULE_PREFIX)
    child = name.rpartition(".")[2]
    if parent is not None and child in vars(parent):
        delattr(parent, child)


def _bind_to_parent(name: str, module: ModuleType) -> None:
    """Make ``plugins.<id>`` an attribute of ``plugins`` too, as an ordinary
    import would, so dotted lookups (``mock.patch("plugins.vestaboard...")``)
    resolve. The parent is core's own ``plugins`` package."""
    try:
        parent = sys.modules.get(MODULE_PREFIX) or importlib.import_module(MODULE_PREFIX)
    except ImportError:
        return
    setattr(parent, name.rpartition(".")[2], module)


def import_first_party_package(source: FirstPartySource) -> ModuleType:
    """Import *source*'s package as ``plugins.<id>`` (once; reused while it
    is the same copy). A copy from elsewhere replaces it, submodules too."""
    name = f"{MODULE_PREFIX}.{source.output_id}"
    init = source.path / "__init__.py"
    existing = sys.modules.get(name)
    if (
        existing is not None
        and getattr(existing, "__file__", None) == str(init)
        and getattr(existing, "__fiestaboard_loaded__", False)
    ):
        return existing
    _evict(name)
    spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[str(source.path)])
    if spec is None or spec.loader is None:
        raise FirstPartyOutputError(f"{source.output_id}: {init} is not an importable package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        _evict(name)
        raise
    module.__fiestaboard_loaded__ = True
    _bind_to_parent(name, module)
    return module


def first_party_module(output_id: str) -> ModuleType:
    """The imported ``plugins.<id>`` package of first-party output
    *output_id*, importing it from the seed (or its dev override) when it is
    not yet. For code that needs its modules by name: tests, scripts.

    Raises:
        FirstPartyOutputError: see :func:`first_party_source`.
    """
    return import_first_party_package(first_party_source(output_id))


def load_first_party(output_id: str, seed_dir: Path | None = None) -> FirstPartyOutput:
    """Load first-party output *output_id* from the seed (or its dev override).

    Raises:
        FirstPartyOutputError: it cannot be found or is refused
            (:func:`first_party_source`), its manifest does not validate, is
            not an output plugin of that id, declares another ``output_api``
            than the lock pins, or the package exports no single
            ``OutputPluginBase`` subclass.
    """
    from src.plugins.manifest import load_manifest

    source = first_party_source(output_id, seed_dir)
    manifest, errors = load_manifest(source.path / "manifest.json")
    if errors or manifest is None:
        raise FirstPartyOutputError(f"{output_id}: manifest.json is invalid: {'; '.join(errors)}")
    if manifest.id != output_id or manifest.plugin_type != "output" or manifest.output is None:
        raise FirstPartyOutputError(f"{output_id}: manifest.json is not the '{output_id}' output plugin")
    if source.output_api is not None and manifest.output.output_api != source.output_api:
        raise FirstPartyOutputError(
            f"{output_id}: manifest output_api is {manifest.output.output_api}, the lock pins {source.output_api}"
        )
    module = import_first_party_package(source)
    classes = [
        value
        for value in vars(module).values()
        if isinstance(value, type) and issubclass(value, OutputPluginBase) and value is not OutputPluginBase
    ]
    if len(classes) != 1:
        raise FirstPartyOutputError(f"{output_id}: the package must export one OutputPluginBase subclass")
    plugin_class = classes[0]
    if not plugin_class.plugin_id:
        plugin_class.plugin_id = manifest.id
    if source.origin == "seed":
        logger.info("Loaded first-party output %s from the seed (commit %s)", output_id, source.commit)
    return FirstPartyOutput(plugin_class, manifest, source)


def _board_grid(board: dict) -> tuple[int, int] | None:
    rows, cols = board.get("grid_rows"), board.get("grid_cols")
    if isinstance(rows, int) and isinstance(cols, int) and rows > 0 and cols > 0:
        return rows, cols
    return None


def _builder(loaded: FirstPartyOutput) -> Callable[[dict], OutputDriver | None]:
    plugin_class, output_manifest = loaded.plugin_class, loaded.manifest.output

    def build(board: dict) -> OutputDriver | None:
        from .board_profile import board_character_set
        from .http import OutputHttp
        from .plugin_driver import OutputPluginDriver

        config = plugin_class.config_from_board(board)
        if config is None:
            return None
        instance = plugin_class(board.get("id"), config)
        # Core's choice, not the plugin's: the requests these outputs always made.
        instance._http = OutputHttp.for_first_party()
        instance.bind_manifest(output_manifest)
        # Only an output whose markup follows its set needs the set resolved
        # (a FiestaPanel's would read the panel store for its render style).
        character_set = board_character_set(board) if plugin_class.markup_follows_charset else None
        instance.bind_board(character_set=character_set, geometry=_board_grid(board))
        instance.open()
        return OutputPluginDriver(instance, character_set=character_set, first_party=True)

    return build


async def _vestaboard_dispatch(call: ActionCall) -> ActionOutcome:
    from .vestaboard.actions import dispatch

    return await dispatch(call)


async def _fiestapanel_dispatch(call: ActionCall) -> ActionOutcome:
    """A FiestaPanel draws in memory: there is no connection to fail."""
    return ActionOutcome(message="FiestaPanel boards render in FiestaBoard itself; there is nothing to connect to.")


#: Core's board-settings action runners for the first-party outputs (their
#: settings screens are still core's own until P4d).
_DISPATCH = {VESTABOARD: _vestaboard_dispatch, FIESTAPANEL: _fiestapanel_dispatch}


def _hooks(output_id: str, plugin_class: type[OutputPluginBase]) -> OutputHooks:
    discover = None
    if getattr(plugin_class.discover, "__func__", None) is not OutputPluginBase.discover.__func__:
        discover = plugin_class.discover
    diagnostics = None
    if hasattr(plugin_class, "diagnose_board"):
        diagnostics = OutputDiagnostics(
            run=plugin_class.diagnose_board,
            advise=plugin_class.diagnostics_advice,
            all_clear=plugin_class.DIAGNOSTICS_ALL_CLEAR,
        )
    actions = plugin_class.hook_actions() if hasattr(plugin_class, "hook_actions") else {}
    return OutputHooks(discover=discover, diagnostics=diagnostics, actions=actions, dispatch=_DISPATCH.get(output_id))


def first_party_definition(output_id: str) -> OutputDefinition:
    """The registry entry of first-party output *output_id*."""
    loaded = load_first_party(output_id)
    manifest = loaded.manifest
    output_manifest = manifest.output
    assert output_manifest is not None
    return OutputDefinition(
        id=manifest.id,
        name=manifest.name,
        capabilities=loaded.plugin_class.declared_capabilities(output_manifest),
        build=_builder(loaded),
        hooks=_hooks(output_id, loaded.plugin_class),
        description=manifest.description,
        icon=manifest.icon,
        actions=output_manifest.actions,
        offered_device_models=_LEGACY_OFFERED_MODELS.get(output_id, output_manifest.device_model_ids),
    )


def register_first_party_outputs(registry: OutputRegistry) -> None:
    """Register every first-party output. One that cannot load is logged and
    left out: its boards stay down with the reason recorded, never another
    output in its place."""
    for output_id in FIRST_PARTY_OUTPUTS:
        try:
            registry.register(first_party_definition(output_id))
        except FirstPartyOutputError as exc:
            logger.error("First-party output %s could not be loaded; its boards cannot be driven: %s", output_id, exc)
        except Exception:
            logger.exception("First-party output %s could not be loaded; its boards cannot be driven", output_id)
