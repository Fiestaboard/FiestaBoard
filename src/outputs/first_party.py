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
with the reason logged.

**In-app updates** (plan D8). Boot gives each one an **installed copy** in
the external plugins directory, copied from the seed
(:func:`~src.outputs.seed.install_first_party_outputs`): a checkout of its
own repository that the Integrations page checks and updates like any plugin,
through the same three ``output_api`` gates — the update check reads the
incoming manifest, a release that does not load is rolled back to the commit
it replaced, and this module's load decides what runs. :func:`load_first_party`
runs the installed copy only when it is **valid and newer than the seed's
pin**: a checkout of the output's own repository (a copy from anywhere else
is never run, whatever its id), a supported ``output_api``, a passing install
self-check, and an import that works. Otherwise the seed's verified copy
runs: silently when the installed copy is the pinned tree or older (an image
upgrade never runs older code), and as a surfaced error (``fallback``) when
it is newer but invalid — the last resort, which also makes an update that
caused it roll back. The seed alone still boots everything offline. They can
be updated, never uninstalled, and never installed from anywhere else.

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
- **Their settings screens are their manifests'**: ``GET /outputs`` carries
  each one's ``settings_schema`` and actions, and the web renders a
  Vestaboard's board settings from them like any output's (plan D13,
  Phase 4 P4d). Its actions, status and ``output_config`` rules are the
  plugin class's, asked like any output's (``handle_action``,
  ``board_status``, :mod:`src.outputs.config_hooks`), so core holds no
  Vestaboard rules (Phase 4 P4e). It still shows no ``output_api`` and
  FiestaPanel's ``vestaboard_panel`` model.
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

from .hooks import OutputDiagnostics, OutputHooks
from .plugin_base import OutputPluginBase
from .registry import FIESTAPANEL, FIRST_PARTY_OUTPUTS, OutputDefinition, OutputRegistry
from .seed import (
    LOCKFILE,
    LockError,
    checkout_origin,
    manifest_version,
    same_repository,
    seed_root,
    seeded_entries,
    tree_digest,
)

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
    "reload_first_party",
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
    #: ``seed`` (digest-verified against the lock), ``installed`` (the
    #: copy in-app updates move, when valid and newer) or ``dev`` (an override).
    origin: Literal["seed", "installed", "dev"]
    #: The pinned commit (``None`` for an installed copy or a dev override).
    commit: str | None
    #: The ``output_api`` the lock pins (``None`` for a dev override).
    output_api: int | None = None


@dataclass(frozen=True)
class FirstPartyOutput:
    """A loaded first-party output: its plugin class, parsed manifest and source."""

    plugin_class: type[OutputPluginBase]
    manifest: PluginManifest
    source: FirstPartySource
    #: Why the installed copy was refused and the seed's runs instead
    #: (an error to surface), or ``None``.
    fallback: str | None = None


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


def _external_plugins_dir() -> Path | None:
    from src.plugins.sources import get_external_plugins_dir

    try:
        return get_external_plugins_dir()
    except OSError as exc:
        logger.warning("No external plugins directory, so no installed first-party outputs: %s", exc)
        return None


def _installed_source(output_id: str, seed: FirstPartySource, external_dir: Path | None) -> FirstPartySource | None:
    """The installed copy of *output_id* to run instead of the seed's, or
    ``None`` when the seed's runs (no copy, the pinned tree, or not newer).

    Raises:
        FirstPartyOutputError: there is a copy, newer than the seed's, but it
            is not a checkout of the output's own repository.
    """
    if external_dir is None:
        return None
    path = Path(external_dir) / output_id
    if not (path / "manifest.json").is_file():
        return None
    pin = seeded_entries(seed.path.parent).get(output_id)
    if pin is None:
        return None
    try:
        if tree_digest(path) == pin.tree_sha256:
            return None  # the pinned tree: the seed's verified copy is the same code
    except LockError as exc:
        raise FirstPartyOutputError(f"{output_id}: the installed copy at {path} is unusable: {exc}") from exc
    have, pinned = manifest_version(path), manifest_version(seed.path)
    if have is not None and pinned is not None and have <= pinned:
        return None  # never older than the image's own copy (boot replaces it)
    origin = checkout_origin(path)
    if not same_repository(origin, pin.repository):
        raise FirstPartyOutputError(
            f"{output_id}: the installed copy at {path} comes from {origin or 'no git repository'}, "
            f"not {pin.repository}; only the output's own repository may update it"
        )
    return FirstPartySource(output_id, path, "installed", None)


def load_first_party(
    output_id: str, seed_dir: Path | None = None, external_dir: Path | None = None
) -> FirstPartyOutput:
    """Load first-party output *output_id*: its dev override, else the
    installed copy when it is valid and newer than the seed's, else the seed.

    The installed copy lives in the external plugins directory
    (*external_dir*, default the loader's), where the Integrations page
    updates it like any plugin (plan D8). It is **valid** when it is a
    checkout of the output's own repository, its manifest validates with a
    supported ``output_api``, it passes the install self-check and it
    imports. An invalid one is refused and the seed's copy runs; that is
    reported in :attr:`FirstPartyOutput.fallback` and logged as an error.

    Raises:
        FirstPartyOutputError: the seed's copy cannot be found or is refused
            (:func:`first_party_source`), or does not load (see
            :func:`_load_source`); or the dev override does not load.
    """
    seed = first_party_source(output_id, seed_dir)
    if seed.origin == "dev":
        return _load_source(seed)
    if external_dir is None:
        external_dir = _external_plugins_dir()
    refusal: str | None = None
    try:
        installed = _installed_source(output_id, seed, external_dir)
        if installed is not None:
            return _load_source(installed)
    except FirstPartyOutputError as exc:
        refusal = str(exc)
    except Exception as exc:
        refusal = f"{output_id}: the installed copy does not import: {exc}"
    loaded = _load_source(seed)
    if refusal is None:
        return loaded
    message = (
        f"The installed copy of '{output_id}' cannot run ({refusal}). Running the copy "
        f"bundled with FiestaBoard (commit {(seed.commit or '?')[:12]}) instead; update or reinstall it."
    )
    logger.error(message)
    return FirstPartyOutput(loaded.plugin_class, loaded.manifest, loaded.source, fallback=message)


def _load_source(source: FirstPartySource) -> FirstPartyOutput:
    """Load the package at *source*.

    Raises:
        FirstPartyOutputError: its manifest does not validate, is not an
            output plugin of that id, declares another ``output_api`` than the
            lock pins, an installed copy fails its install self-check, or the
            package exports no single ``OutputPluginBase`` subclass.
    """
    from src.plugins.manifest import load_manifest

    output_id = source.output_id
    manifest, errors = load_manifest(source.path / "manifest.json")
    if errors or manifest is None:
        raise FirstPartyOutputError(f"{output_id}: manifest.json is invalid: {'; '.join(errors)}")
    if manifest.id != output_id or manifest.plugin_type != "output" or manifest.output is None:
        raise FirstPartyOutputError(f"{output_id}: manifest.json is not the '{output_id}' output plugin")
    if source.output_api is not None and manifest.output.output_api != source.output_api:
        raise FirstPartyOutputError(
            f"{output_id}: manifest output_api is {manifest.output.output_api}, the lock pins {source.output_api}"
        )
    if source.origin == "installed":
        from src.plugins.install_check import validate_install

        check = validate_install(output_id, source.path, manifest)
        if check.errors:
            raise FirstPartyOutputError(
                f"{output_id}: the installed copy fails its self-check: {'; '.join(check.errors)}"
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
    elif source.origin == "installed":
        logger.info("Loaded first-party output %s %s from its installed copy", output_id, manifest.version)
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


def _hooks(plugin_class: type[OutputPluginBase]) -> OutputHooks:
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
    return OutputHooks(discover=discover, diagnostics=diagnostics)


def first_party_definition(output_id: str) -> OutputDefinition:
    """The registry entry of first-party output *output_id*."""
    return _definition(load_first_party(output_id))


def reload_first_party(
    output_id: str, *, seed_dir: Path | None = None, external_dir: Path | None = None
) -> FirstPartyOutput:
    """Load first-party output *output_id* again (:func:`load_first_party`)
    and make what loaded the output registry's entry for it — still a
    first-party entry, never a plugin one. The plugin loader calls this for
    the output's installed copy (boot, update, reload). An entry already
    built from the same plugin class is kept, so a board's runtime is only
    rebuilt when the code that drives it changed.

    Raises:
        FirstPartyOutputError: see :func:`load_first_party`.
    """
    from .registry import output_registry

    loaded = load_first_party(output_id, seed_dir, external_dir)
    registry = output_registry()
    current = registry.get(output_id)
    if current is None or current.plugin_class is not loaded.plugin_class:
        registry.put_first_party(_definition(loaded))
    return loaded


def _definition(loaded: FirstPartyOutput) -> OutputDefinition:
    output_id = loaded.source.output_id
    manifest = loaded.manifest
    output_manifest = manifest.output
    assert output_manifest is not None
    return OutputDefinition(
        id=manifest.id,
        name=manifest.name,
        capabilities=loaded.plugin_class.declared_capabilities(output_manifest),
        build=_builder(loaded),
        hooks=_hooks(loaded.plugin_class),
        description=manifest.description,
        icon=manifest.icon,
        actions=output_manifest.actions,
        settings_schema=output_manifest.settings_schema,
        offered_device_models=_LEGACY_OFFERED_MODELS.get(output_id, output_manifest.device_model_ids),
        plugin_class=loaded.plugin_class,
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
