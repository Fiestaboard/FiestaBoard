"""Plugin orchestration service (issue #1757).

One place for the mutate → persist → reset-display → reset-template-engine
sequence that five REST handlers used to copy-paste (config update, enable,
disable, instance create, instance delete), and the only code allowed to
touch ``ConfigManager._mask_sensitive`` and ``PluginRegistry._update_status``
— routes and MCP tools go through the public wrappers here instead.

Collaborators resolve in one of two ways:

* The REST handlers in ``src/plugins/routes.py`` construct the service with
  the registry / config-manager / reset callables they resolved through
  ``src.api_server`` at call time, so the suite's
  ``patch("src.api_server.<name>")`` seams keep working (the #1756 pattern).
* Everything else (the MCP server, background tasks) constructs it bare —
  ``PluginService()`` — and each collaborator resolves lazily from its
  canonical home (``src.plugins``, ``src.config_manager``,
  ``src.displays.service``, ``src.templates.engine``). That lazy resolution
  is what breaks the api_server ↔ mcp_server dependency: the plugin MCP
  tools no longer import ``src.api_server`` at all, and the patch targets
  ``src.plugins.get_plugin_registry`` / ``src.config_manager
  .get_config_manager`` used by the MCP suite stay live.

Error contract: methods raise the domain exceptions in
:mod:`src.plugins.errors` and know nothing about HTTP. Phase 1 had this
service raising a FastAPI transport exception at 25 sites — the one service in
the tree that knew a status code, and the layering violation the 2026-09 audit
called out. The REST router owns the mapping now
(``src/plugins/routes.py::_STATUS_BY_ERROR``); the MCP/ops layer catches the
same exceptions and renders its own envelope without going near a status code.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.config_manager import unmask_sensitive_values

from .errors import (
    PluginConfigInvalid,
    PluginNotFound,
    PluginOperationFailed,
    PluginOperationRejected,
)

logger = logging.getLogger(__name__)

_PLUGIN_ID_RE = re.compile(r"^[a-z0-9_]+$")


def sanitize_optional_plugin_id(plugin_id: str | None) -> str | None:
    """Validate an optional plugin id from user input.

    Accepts ``None`` (meaning "derive from repo name"), otherwise enforces
    lowercase letters, digits, and underscores only.
    """
    if plugin_id is None:
        return None
    if not isinstance(plugin_id, str) or not plugin_id:
        raise PluginOperationRejected("plugin_id must be a non-empty string")
    if not _PLUGIN_ID_RE.fullmatch(plugin_id):
        raise PluginOperationRejected("plugin_id may contain only lowercase letters, digits, and underscores")
    return plugin_id


class PluginService:
    """Owns every plugin mutation's orchestration sequence."""

    def __init__(
        self,
        registry: Any | None = None,
        config_manager: Any | None = None,
        reset_display: Callable[[], None] | None = None,
        reset_template: Callable[[], None] | None = None,
        page_service: Any | None = None,
        settings_service: Any | None = None,
    ) -> None:
        self._registry = registry
        self._config_manager = config_manager
        self._reset_display = reset_display
        self._reset_template = reset_template
        self._page_service = page_service
        self._settings_service = settings_service

    # -- collaborator resolution --------------------------------------------

    @property
    def registry(self) -> Any:
        if self._registry is not None:
            return self._registry
        from src.plugins import get_plugin_registry  # canonical home; patched by the MCP suite

        return get_plugin_registry()

    @property
    def config_manager(self) -> Any:
        if self._config_manager is not None:
            return self._config_manager
        from src.config_manager import get_config_manager  # canonical home; patched by the MCP suite

        return get_config_manager()

    @property
    def page_service(self) -> Any:
        if self._page_service is not None:
            return self._page_service
        from src.pages.service import get_page_service

        return get_page_service()

    @property
    def settings_service(self) -> Any:
        if self._settings_service is not None:
            return self._settings_service
        from src.settings.service import get_settings_service

        return get_settings_service()

    # -- the one orchestration tail -----------------------------------------

    def reset_runtime(self) -> None:
        """Reset the display service and template engine after a mutation.

        This is the tail of every plugin mutation — the sequence that used to
        be copy-pasted after each of the five mutating handlers. Written once,
        here.
        """
        if self._reset_display is not None:
            self._reset_display()
        else:
            from src.displays.service import reset_display_service

            reset_display_service()
        if self._reset_template is not None:
            self._reset_template()
        else:
            from src.templates.engine import reset_template_engine

            reset_template_engine()

    # -- private-member wrappers --------------------------------------------

    def mask_config(self, config: dict[str, Any] | None) -> dict[str, Any]:
        """Return *config* with sensitive fields masked, ``{}`` for empty.

        ``ConfigManager._mask_sensitive`` is the one masking implementation;
        the private reach lives here (once) so no route touches it.
        """
        if not config:
            return {}
        return self.config_manager._mask_sensitive(config)

    def clear_update_status(self, plugin_id: str) -> None:
        """Forget the cached "update available" flag after applying an update.

        Delegates to the registry so the cache is mutated under the registry
        lock (#1828) rather than poked at from out here.
        """
        self.registry.clear_update_status(plugin_id)

    # -- reads ---------------------------------------------------------------

    async def fetch_data(self, plugin_id: str) -> Any:
        """The plugin's current data, with an unavailable plugin *reported*.

        Returns the registry's own :class:`~src.plugins.base.PluginResult`.
        Only one outcome raises: :class:`PluginNotFound`, for an id the
        registry has never heard of, because that is a mistake in the request
        rather than a fact about the plugin. Disabled, unconfigured, a
        transition plugin with no data, and a fetch that threw all come back
        ``available=False`` with the reason in ``error`` — the registry
        already distinguishes those four, and flattening them into one
        refusal throws that away.

        ``fetch_plugin_data`` makes network calls, so it runs on a worker
        thread. Inline it would seize the single event loop for the whole
        fetch (``tests/test_plugin_data_event_loop.py``).
        """
        registry = self.registry
        if registry.get_plugin(plugin_id) is None:
            raise PluginNotFound(f"Plugin not found: {plugin_id}")
        return await asyncio.to_thread(registry.fetch_plugin_data, plugin_id)

    async def browse_options(
        self,
        plugin_id: str,
        options_id: str,
        *,
        parent: dict[str, Any] | None = None,
        query: str = "",
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Browse one of the plugin's remote-options catalogs (one lookup, no cache).

        The same provider ``POST /plugins/{id}/options/{options_id}`` serves
        the settings form's picker from, minus the keystroke-driven cache,
        refresh throttle and draft-config overlay — an assistant asks once,
        against the stored config, after :meth:`update_plugin_config`. The
        payload shape is the endpoint's (``options``, ``has_more``,
        ``cursor``, ``total``, ``error``), and the same ceilings apply: the
        registry's worker-thread deadline and the option-count cap.

        Raises :class:`PluginNotFound` for an unknown plugin,
        :class:`PluginOperationRejected` for an ``options_id`` the manifest
        does not declare, and :class:`PluginOperationFailed` when the
        provider is unimplemented, times out, or throws. "Cannot answer yet"
        (:class:`~src.plugins.base.OptionsUnavailable`) is not a failure: it
        comes back as an empty list with the reason in ``error``.
        """
        from .base import OptionsRequest, OptionsUnavailable
        from .options_runtime import (
            PLUGIN_OPTIONS_MAX_CURSOR_CHARS,
            PLUGIN_OPTIONS_MAX_RETURNED,
            PLUGIN_OPTIONS_TIMEOUT_SECONDS,
            _bounded_options_call,
            _declared_options_ids,
            _serialise_options,
            _truncate,
        )

        registry = self.registry
        if registry.get_plugin(plugin_id) is None:
            raise PluginNotFound(f"Plugin not found: {plugin_id}")

        declared = _declared_options_ids(registry.get_manifest(plugin_id))
        if options_id not in declared:
            known = ", ".join(sorted(declared)) or "none"
            raise PluginOperationRejected(
                f"Plugin '{plugin_id}' does not declare options provider '{options_id}' (declared: {known})"
            )

        limit = max(1, min(limit, PLUGIN_OPTIONS_MAX_RETURNED))
        request = OptionsRequest(
            options_id=options_id,
            parent=dict(parent or {}),
            query=query or "",
            limit=limit,
            cursor=cursor,
        )

        def _envelope(**overrides: Any) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "plugin_id": plugin_id,
                "options_id": options_id,
                "options": [],
                "has_more": False,
                "cursor": None,
                "total": None,
                "error": None,
            }
            payload.update(overrides)
            return payload

        try:
            result = await _bounded_options_call(
                lambda: registry.get_plugin_options(plugin_id, options_id, request),
                PLUGIN_OPTIONS_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise PluginOperationFailed(f"Options provider '{options_id}' timed out") from exc
        except NotImplementedError as exc:
            raise PluginOperationFailed(str(exc)) from exc
        except KeyError as exc:
            raise PluginNotFound(f"Plugin not found: {plugin_id}") from exc
        except OptionsUnavailable as exc:
            return _envelope(error=str(exc))
        except Exception as exc:
            # Traceback to the log; the caller gets a static message so a
            # plugin's raw error text (keys, URLs, paths) cannot leak.
            logger.exception("Options provider '%s' failed for plugin '%s'", options_id, plugin_id)
            raise PluginOperationFailed("Options provider failed") from exc

        options, truncated = _serialise_options(result.options, limit, plugin_id, options_id)
        return _envelope(
            options=options,
            has_more=bool(result.has_more) or truncated,
            cursor=_truncate(result.cursor, PLUGIN_OPTIONS_MAX_CURSOR_CHARS),
            total=result.total,
            error=result.error,
        )

    # -- demo pages ----------------------------------------------------------

    def resolve_demo_device_type(self, demo: dict[str, Any]) -> str:
        """Pick the demo device_type that matches the configured board.

        Walks the user's configured boards in order and returns the first
        device_type that the plugin actually ships a demo for. Falls back to
        any device_type the plugin supports, then to "flagship" as a last
        resort. See issue #942.
        """
        configured: list[str] = []
        try:
            board_settings = self.settings_service.get_board_settings()
            for board in getattr(board_settings, "boards", []) or []:
                dt = board.get("device_type") if isinstance(board, dict) else None
                if dt and dt not in configured:
                    configured.append(dt)
        except Exception:
            logger.debug("Could not resolve configured device_type; using plugin default", exc_info=True)

        for dt in configured:
            if dt in demo:
                return dt
        if demo:
            return next(iter(demo))
        return "flagship"

    def demo_page_status(self, plugin_id: str, device_type: str = "flagship") -> dict[str, Any]:
        """Whether a demo page exists for this plugin and device type.

        Returns ``{"exists", "page_id", "has_demo_template"}`` — the
        ``GET /plugins/{id}/demo-page`` payload. Raises
        :class:`PluginNotFound` for an unknown plugin.
        """
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            raise PluginNotFound(f"Plugin not found: {plugin_id}")
        if manifest.demo is None:
            return {"exists": False, "page_id": None, "has_demo_template": False}

        demo_page = self.page_service.get_demo_page(plugin_id, device_type=device_type)
        return {
            "exists": demo_page is not None,
            "page_id": demo_page.id if demo_page else None,
            "has_demo_template": device_type in manifest.demo,
        }

    def create_demo_page(
        self,
        plugin_id: str,
        device_type: str | None = None,
        *,
        recreate: bool = True,
    ) -> dict[str, Any]:
        """Create (or recreate) the demo page for a plugin and device type.

        When *device_type* is omitted it is resolved from the configured
        board settings, so a Note board does not silently get a
        Flagship-sized demo page (issue #942). The demo page is a singleton
        per plugin + device type. With ``recreate=True`` (the REST default)
        an existing page is deleted and rebuilt; with ``recreate=False`` an
        existing page is left alone and returned, so an assistant does not
        throw away a demo page the user has since edited.

        Returns ``{"page", "created", "recreated", "device_type"}``:
        ``created`` is False only when an existing page was kept.

        Raises :class:`PluginNotFound` for an unknown plugin and
        :class:`PluginOperationRejected` when the plugin ships no demo for
        that device type or its required settings are not configured yet.
        """
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            raise PluginNotFound(f"Plugin not found: {plugin_id}")

        if manifest.demo is None:
            raise PluginOperationRejected(f"Plugin '{plugin_id}' does not include a demo page template.")

        resolved_device_type = device_type or self.resolve_demo_device_type(manifest.demo)

        demo_schema = manifest.demo.get(resolved_device_type)
        if demo_schema is None:
            raise PluginOperationRejected(
                f"Plugin '{plugin_id}' has no demo template for device type '{resolved_device_type}'."
            )

        required_fields = manifest.settings_schema.get("required", [])
        if required_fields:
            plugin_config = self.config_manager.get_plugin_config(plugin_id) or {}
            missing = [f for f in required_fields if f != "enabled" and not plugin_config.get(f)]
            if missing:
                raise PluginOperationRejected(
                    f"Required settings not configured: {', '.join(missing)}. "
                    f"Configure them first before creating a demo page."
                )

        page_service = self.page_service
        if not recreate:
            existing = page_service.get_demo_page(plugin_id, device_type=resolved_device_type)
            if existing is not None:
                return {"page": existing, "created": False, "recreated": False, "device_type": resolved_device_type}

        page, recreated = page_service.create_demo_page(plugin_id, demo_schema)
        return {"page": page, "created": True, "recreated": recreated, "device_type": resolved_device_type}

    # -- config / enablement mutations --------------------------------------

    def update_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Validate, persist, and apply a plugin configuration.

        Returns the stored config, masked, for echoing back to the caller.
        """
        registry = self.registry
        if not registry.get_plugin(plugin_id):
            raise PluginNotFound(f"Plugin not found: {plugin_id}")

        # Resolve the "***" placeholders before anything sees the payload.
        # Config goes out masked, so any client that echoes back what it read
        # — the settings form, or an MCP client working from
        # list_installed_plugins() — posts the sentinel where the secret used
        # to be. Un-masking here rather than only inside ConfigManager keeps
        # the mask out of the live plugin as well, whose validate_config() /
        # on_config_change() would otherwise run against three asterisks
        # (issue #1743). Raw STORED config, WITHOUT the env-var overlay:
        # this value feeds the un-mask + persist path, and resolving "***"
        # from the overlay would silently write an env secret into
        # config.json (issue #1761 / #1865 review).
        config_manager = self.config_manager
        stored_config = config_manager.get_plugin_config(plugin_id, include_env_overrides=False) or {}
        config = unmask_sensitive_values(config, stored_config)

        # Validate configuration against manifest schema
        errors = registry.set_plugin_config(plugin_id, config)
        if errors:
            logger.error(f"Plugin '{plugin_id}' config validation failed: {errors}")
            raise PluginConfigInvalid(f"Configuration for '{plugin_id}' failed validation.", errors)

        # Save to config file
        config_manager.set_plugin_config(plugin_id, config)

        # Re-seed the LIVE registry config from the overlaid read. Persisting
        # env-free is correct, but the validation call above also installed
        # that env-free dict as the live config — killing a working
        # env-supplied credential until restart (#1864 review). Named
        # instances never have an overlay, so this is a no-op for them.
        live_config = config_manager.get_plugin_config(plugin_id)
        if live_config is not None and live_config != config:
            reseed_errors = registry.set_plugin_config(plugin_id, live_config)
            if reseed_errors:
                # The stored config validated; only the env overlay can be at
                # fault. Keep the env-free live config rather than failing
                # the save the user just made.
                logger.warning(
                    f"Env overlay for '{plugin_id}' failed validation after save: {reseed_errors} "
                    "— live config runs without the overlay until restart"
                )

        # Reset services to pick up new config
        self.reset_runtime()

        logger.info(f"Plugin '{plugin_id}' configuration updated")

        return self.mask_config(config_manager.get_plugin_config(plugin_id))

    def enable_plugin(self, plugin_id: str) -> None:
        """Enable a plugin in the registry and persist the flag to config."""
        registry = self.registry
        if not registry.get_plugin(plugin_id):
            raise PluginNotFound(f"Plugin not found: {plugin_id}")

        if not registry.enable_plugin(plugin_id):
            raise PluginOperationRejected(f"Failed to enable plugin: {plugin_id}")

        self.config_manager.enable_plugin(plugin_id)
        self.reset_runtime()

        logger.info(f"Plugin '{plugin_id}' enabled")

    def disable_plugin(self, plugin_id: str) -> None:
        """Disable a plugin in the registry and persist the flag to config."""
        registry = self.registry
        if not registry.get_plugin(plugin_id):
            raise PluginNotFound(f"Plugin not found: {plugin_id}")

        if not registry.disable_plugin(plugin_id):
            raise PluginOperationRejected(f"Failed to disable plugin: {plugin_id}")

        self.config_manager.disable_plugin(plugin_id)
        self.reset_runtime()

        logger.info(f"Plugin '{plugin_id}' disabled")

    # -- instances -----------------------------------------------------------

    def create_instance(self, plugin_id: str, label: str) -> tuple[str, str]:
        """Create a plugin instance; returns ``(base_id, compound_key)``.

        The caller reads the normalized label back out of the compound key —
        that is the instance the registry holds and the one
        ``{{plugin:label.field}}`` template references must use.
        """
        registry = self.registry

        base_id, _ = registry.parse_instance_key(plugin_id)

        if not registry.get_plugin(base_id):
            raise PluginNotFound(f"Plugin not found: {base_id}")

        errors = registry.create_instance(base_id, label)
        if errors:
            raise PluginOperationRejected("; ".join(errors))

        compound_key = registry.make_instance_key(base_id, label)

        config_manager = self.config_manager
        # The registry can come up without its named instances — an unreadable
        # config.json, or a base plugin that failed to load, both leave the
        # stored entries untouched but drop the live instances. The UI then
        # shows nothing and the user re-adds the label by hand. Blindly
        # persisting an empty config here used to overwrite their saved
        # settings with `{"enabled": false}`, so the plugin fell back to
        # manifest defaults. Adopt whatever is still on disk instead.
        stored = config_manager.get_plugin_config(compound_key)
        if stored:
            errors = registry.apply_stored_config(compound_key, stored)
            if errors:
                logger.warning(
                    "Adopted stored config for re-created instance '%s' despite validation errors: %s",
                    compound_key,
                    errors,
                )
            if stored.get("enabled"):
                registry.enable_plugin(compound_key)
            logger.info("Re-created instance '%s' adopted its existing stored config", compound_key)
        else:
            # Persist empty config so the instance survives restarts
            config_manager.set_plugin_config(compound_key, {"enabled": False})
        # Re-creating an instance is an explicit user action — drop any
        # deliberate-removal tombstone left by a prior delete (#1394).
        config_manager.clear_plugin_removed(compound_key)

        # Reset services so the new instance is available to templates immediately
        self.reset_runtime()

        logger.info(f"Created plugin instance: {compound_key}")
        return base_id, compound_key

    def delete_instance(self, plugin_id: str, instance_label: str) -> tuple[str, str]:
        """Delete a plugin instance; returns ``(base_id, compound_key)``.

        Raises :class:`PluginNotFound` when the instance does not exist, so
        ``DELETE /plugins/{id}/instances/{label}`` answers the 404 it declares.
        The registry reports the missing case as an error *string*, which used
        to be wrapped in :class:`PluginOperationRejected` and served as a 400 —
        while the ``create_instance`` on the very same path already raised
        :class:`PluginNotFound`. See review finding 6.
        """
        registry = self.registry

        base_id, _ = registry.parse_instance_key(plugin_id)
        compound_key = registry.make_instance_key(base_id, instance_label)

        # Mirrors the registry's own `compound_key not in self._plugins` check.
        if registry.get_plugin(compound_key) is None:
            raise PluginNotFound(f"Instance not found: {compound_key}")

        errors = registry.delete_instance(base_id, instance_label)
        if errors:
            raise PluginOperationRejected("; ".join(errors))

        # Remove persisted config and tombstone the compound key so a
        # post-upgrade auto-restore cannot resurrect the deleted instance (#1394).
        config_manager = self.config_manager
        config_manager.delete_plugin_config(compound_key)
        config_manager.mark_plugin_removed(compound_key)

        self.reset_runtime()

        logger.info(f"Deleted plugin instance: {compound_key}")
        return base_id, compound_key

    # -- install / uninstall / update ----------------------------------------

    async def install_from_registry(self, plugin_id: str) -> None:
        """Install a plugin from the curated registry by its id.

        The install shells out to ``git`` (up to 120 s) and then imports the
        plugin package, so it runs in a worker thread — inline it would seize
        the event loop and freeze every other request for the whole clone
        (#1750).
        """
        registry = self.registry
        errors = await asyncio.to_thread(registry.install_from_registry, plugin_id)
        if errors:
            raise PluginOperationRejected("; ".join(errors))

    async def install_from_git(self, repository: str, plugin_id: str | None = None, branch: str = "") -> str:
        """Install a plugin from a public git repository URL; returns its id.

        The clone runs in a worker thread so a slow or unreachable remote
        cannot block the event loop (#1750).
        """
        safe_branch = branch or ""
        if safe_branch:
            from .sources import _validate_git_ref

            _ok, _err = _validate_git_ref(safe_branch)
            if not _ok:
                raise PluginOperationRejected(_err)

        safe_plugin_id = sanitize_optional_plugin_id(plugin_id)

        registry = self.registry
        errors = await asyncio.to_thread(
            registry.install_from_git,
            repository,
            plugin_id=safe_plugin_id,
            branch=safe_branch,
        )
        if errors:
            raise PluginOperationRejected("; ".join(errors))

        # Derive the final plugin id
        pid = safe_plugin_id
        if pid is None:
            from .sources import plugin_id_from_repo_name, repo_name_from_url

            pid = plugin_id_from_repo_name(repo_name_from_url(repository))
        return pid

    def uninstall(self, plugin_id: str) -> None:
        """Uninstall an external plugin and purge its persisted configs.

        Raises :class:`PluginNotFound` when the plugin has no source at all, so
        ``DELETE /plugins/{id}/uninstall`` answers the 404 it declares.
        Uninstalling a nonexistent plugin used to answer 400 with the literal
        text "Plugin not found", because the registry reports that case as an
        error *string*. A built-in is still a 400: it exists, and refusing to
        remove it is a rule, not a missing resource. See review finding 6.
        """
        registry = self.registry

        # Mirrors the registry's own `source is None` check, ahead of it so the
        # verdict is a 404 rather than a rejection.
        if registry.get_plugin_source(plugin_id) is None:
            raise PluginNotFound(f"Plugin not found: {plugin_id}")

        # Collect instance compound keys before uninstall so we can purge their configs
        instance_keys = [
            p["id"] for p in registry.list_plugins() if p.get("base_plugin_id") == plugin_id and p.get("instance_label")
        ]

        errors = registry.uninstall_external_plugin(plugin_id)
        if errors:
            raise PluginOperationRejected("; ".join(errors))

        # Purge persisted configs for both the base plugin and every named
        # instance. The base-id delete is critical: without it the v2→v3
        # auto-migration would see the leftover entry as orphaned on the next
        # boot and silently reinstall the plugin the user just deleted (#937).
        config_manager = self.config_manager
        for compound_key in instance_keys:
            config_manager.delete_plugin_config(compound_key)
        config_manager.delete_plugin_config(plugin_id)

    def _validated_update_path(self, plugin_id: str) -> None:
        """Guard an external plugin's local path before letting it near git.

        :class:`PluginNotFound` when the plugin has no source at all;
        :class:`PluginOperationRejected` for built-ins, missing paths, paths
        outside the external plugins directory, and non-repos — exactly the
        checks the REST handler applied inline, minus the status codes.
        """
        import os as _os

        from .sources import get_external_plugins_dir

        source = self.registry.get_plugin_source(plugin_id)

        if source is None:
            raise PluginNotFound(f"Plugin '{plugin_id}' not found.")

        if source.source_type == "builtin":
            raise PluginOperationRejected(f"Plugin '{plugin_id}' is a built-in plugin and cannot be updated this way.")

        if not source.local_path:
            raise PluginOperationRejected(f"Plugin '{plugin_id}' has no local path for updating.")

        # Verify the plugin's local_path is within the external plugins
        # directory before updating, as a defence-in-depth check.
        _ext_root = _os.path.realpath(str(get_external_plugins_dir()))
        _real_local = _os.path.realpath(str(source.local_path))
        try:
            _common = _os.path.commonpath([_ext_root, _real_local])
        except ValueError:
            raise PluginOperationRejected("Invalid plugin path.") from None
        if _common != _ext_root or _real_local == _ext_root:
            raise PluginOperationRejected("Invalid plugin path.")

        if not (_real_local and (Path(_real_local) / ".git").is_dir()):
            raise PluginOperationRejected(f"Plugin '{plugin_id}' is not a git repository.")

    async def apply_update(self, plugin_id: str) -> None:
        """Fetch the latest commits for an external plugin and reload it."""
        from .sources import clone_or_update_repo, get_external_plugins_dir

        registry = self.registry
        self._validated_update_path(plugin_id)

        # Pass the validated plugin_id — clone_or_update_repo resolves the
        # path internally so no user-controlled Path flows into subprocess
        # sinks. Both the git fetch and the module reimport go to a worker
        # thread so the event loop keeps serving other requests during the
        # update (#1750).
        ok, err = await asyncio.to_thread(clone_or_update_repo, "", plugin_id, external_dir=get_external_plugins_dir())
        if not ok:
            raise PluginOperationFailed(f"Update failed: {err}")

        reloaded = await asyncio.to_thread(registry.reload_plugin, plugin_id)
        if reloaded is None:
            errors = registry.get_load_errors().get(plugin_id, [])
            detail = "; ".join(errors) if errors else "Plugin failed to reload after update."
            raise PluginOperationFailed(detail)

        self.clear_update_status(plugin_id)

    async def apply_all_updates(self) -> dict[str, Any]:
        """Fetch and reload every external plugin with a pending update.

        Uses the cached update status from the last check. Never raises for a
        single plugin's failure — the caller gets partial results.
        """
        import os as _os

        from .sources import clone_or_update_repo, get_external_plugins_dir

        registry = self.registry
        pending = [pid for pid, has_update in registry.get_update_status().items() if has_update]

        if not pending:
            return {"updated": [], "failed": {}, "message": "No updates available."}

        updated: list[str] = []
        failed: dict[str, str] = {}
        _ext_dir = get_external_plugins_dir()
        _ext_root = _os.path.realpath(str(_ext_dir))

        for plugin_id in pending:
            source = registry.get_plugin_source(plugin_id)
            if source is None or not source.local_path:
                failed[plugin_id] = "Plugin source not found."
                continue

            _real_local = _os.path.realpath(str(Path(source.local_path)))
            try:
                _common = _os.path.commonpath([_ext_root, _real_local])
            except ValueError:
                failed[plugin_id] = "Invalid plugin path."
                continue
            if _common != _ext_root or _real_local == _ext_root:
                failed[plugin_id] = "Invalid plugin path."
                continue
            if not (Path(_real_local) / ".git").is_dir():
                failed[plugin_id] = "Plugin is not a git repository."
                continue

            # Pass the validated plugin_id — clone_or_update_repo resolves the
            # path internally so no user-controlled Path flows into subprocess
            # sinks. A bulk update is N sequential git fetches; keeping them on
            # the loop would freeze the API for the sum of all of them (#1750).
            ok, err = await asyncio.to_thread(clone_or_update_repo, "", plugin_id, external_dir=_ext_dir)
            if not ok:
                failed[plugin_id] = f"git fetch failed: {err}"
                continue

            reloaded = await asyncio.to_thread(registry.reload_plugin, plugin_id)
            if reloaded is None:
                errors = registry.get_load_errors().get(plugin_id, [])
                failed[plugin_id] = "; ".join(errors) if errors else "Reload failed."
                continue

            self.clear_update_status(plugin_id)
            updated.append(plugin_id)
            logger.info("Bulk update: applied update for plugin '%s'", plugin_id)

        return {
            "updated": updated,
            "failed": failed,
            "message": f"Updated {len(updated)} plugin(s); {len(failed)} failed.",
        }
