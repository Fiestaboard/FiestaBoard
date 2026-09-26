"""Value-level contract goldens for the /plugins API (Phase 2 §2, slice 4).

These are deliberately *values*, not shapes. The shape corpus in
``tests/golden/responses/plugins.json`` records key sets and type names, so it
cannot see a secret replaced by three asterisks, an env value written into
``config.json``, a plugin id echoed back wrong, or an error string that stopped
naming the missing plugin.

That is not hypothetical here. The masking round-trip is the highest-stakes
contract in this codebase: an independent audit found a regression in it that
the shape golden provably could not catch (#1743), and a later PR nearly
reintroduced it during a merge (#1864 review). The three facts pinned by
:class:`TestMaskedSecretRoundTrip` and :class:`TestEnvOverrideRoundTrip` —
by value, against a **real** ``ConfigManager`` writing a **real** file — are
what stop that from happening a third time:

1. a masked field posted back as ``"***"`` persists the STORED secret, never
   the literal ``"***"``;
2. with an env override active, the persisted value stays the stored one while
   the LIVE plugin config carries the env value;
3. ``env_overridden_keys`` names exactly the keys the environment controls,
   and their values never appear in ``config``.

Covers all 25 routes the ``plugins`` router serves, success and failure paths.

Re-pinned by the conventions pass in the following commit. What deliberately
changed, and nothing else:

* Creates answer **201**: ``POST /plugins/{id}/instances``,
  ``POST /plugins/{id}/demo-page``, ``POST /plugins/install`` and
  ``POST /plugins/registry/{id}/install`` — conventions doc, "Status codes".
* ``"status": "success"`` is gone from the config-update, enable, disable,
  instance create/delete, install, uninstall and update bodies. The status
  code already carried it.
* ``POST /plugins/{id}/demo-page`` reports ``recreated: bool`` instead of
  ``status: "created" | "recreated"``.
* ``POST /plugins/{id}/receive`` **keeps** its ``{"status": "ok"}`` — it is a
  webhook target for third-party systems this repo cannot update in lockstep —
  and gains ``plugin_id`` so the ack names what it acked.
* The 400 on schema validation now carries ``detail.message`` alongside
  ``detail.errors``; a dict detail with no message is the exact anti-pattern
  the conventions doc bans.
* ``GET /plugins/errors`` gains ``fetch_breakers``, exposing
  ``registry.get_fetch_breaker_status()`` for the first time.
* Registry entries and instance infos always carry their full declared key
  set (defaults where the source is silent) instead of whatever keys the
  producer happened to include — recipe addendum 4, the "sometimes-absent
  key" anti-pattern.

Every other value assertion — ids, masked secrets, env-override behavior,
error strings, the 400/403/404/405/503 status codes — is unchanged from the
pre-conversion recording. None was weakened.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.config_manager import ConfigManager

REAL_SECRET = "super-secret-key-abc123"
MASK = "***"


# ── Stubs ───────────────────────────────────────────────────────────────────


class _ContractRegistry:
    """Deterministic registry covering the whole /plugins route family.

    Mirrors the stub in ``tests/test_response_shape_goldens.py`` so the two
    corpora describe the same world; the difference is what is asserted about
    it, not what it is.
    """

    def __init__(self) -> None:
        self.enabled: dict[str, bool] = {"alpha": True, "ext_plugin": False}
        self.config_errors: list[str] = []
        self.enable_ok = True
        self.applied: list[dict[str, Any]] = []
        alpha_manifest = SimpleNamespace(
            name="Alpha",
            version="1.0.0",
            description="Contract fixture plugin 'alpha'.",
            author="Contract Fixtures",
            icon="sparkles",
            category="utility",
            plugin_type="data",
            settings_schema={
                "type": "object",
                "required": ["api_key"],
                "properties": {
                    "api_key": {"type": "string", "title": "API Key"},
                    "location": {"type": "string", "title": "Location"},
                    "symbols": {
                        "type": "array",
                        "ui:widget": "remote-options",
                        "ui:options": {"options_id": "symbols", "cache_seconds": 0},
                    },
                },
            },
            max_lengths={"value": 10},
            env_vars=[],
            documentation=None,
            demo={"flagship": {"name": "Alpha Demo", "template": ["ALPHA"]}},
            raw={
                "variables": {"value": {"description": "A value", "example": "X"}},
                "color_rules_schema": {},
                "options": [{"id": "symbols", "cache_seconds": 0}],
            },
        )
        no_demo_manifest = SimpleNamespace(
            name="No Demo",
            version="0.2.0",
            description="Fixture without a demo template.",
            author="Contract Fixtures",
            icon=None,
            category="utility",
            plugin_type="data",
            settings_schema={},
            max_lengths={},
            env_vars=[],
            documentation=None,
            demo=None,
            raw={"variables": {}},
        )
        self.manifests = {"alpha": alpha_manifest, "norecv": no_demo_manifest}
        # "alpha:work" is held because list_instances() reports it — a fake
        # that advertises an instance it does not hold cannot exercise the
        # instance delete path honestly.
        self.plugins = {"alpha": Mock(), "norecv": Mock(), "ext_plugin": Mock(), "alpha:work": Mock()}
        self.fetch_result = SimpleNamespace(
            available=True,
            data={"value": 42},
            formatted_lines=["ALPHA 42"],
            error=None,
        )
        self.update_status = {"ext_plugin": True, "quiet_plugin": False}
        self.sources = {
            "ext_plugin": SimpleNamespace(source_type="git", local_path=None),
            "alpha": SimpleNamespace(source_type="builtin", local_path=None),
        }

    # -- read surface -------------------------------------------------------
    def list_plugins(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "alpha",
                "name": "Alpha",
                "version": "1.0.0",
                "description": "Contract fixture plugin 'alpha'.",
                "enabled": True,
                "base_plugin_id": None,
                "instance_label": None,
            },
            {
                "id": "ext_plugin",
                "name": "Ext Plugin",
                "version": "0.1.0",
                "description": "Contract fixture external plugin.",
                "enabled": False,
                "base_plugin_id": None,
                "instance_label": None,
            },
        ]

    def get_all_variables(self) -> dict[str, Any]:
        return {"alpha": {"value": {"description": "A value", "example": "X"}}}

    def get_all_max_lengths(self) -> dict[str, Any]:
        return {"alpha": {"value": 10}}

    def get_load_errors(self) -> dict[str, Any]:
        return {"broken_plugin": ["ImportError: contract fixture"]}

    def get_fetch_breaker_status(self) -> dict[str, dict[str, Any]]:
        return {
            "slow_plugin": {
                "consecutive_timeouts": 3,
                "quarantined": True,
                "cooldown_remaining_seconds": 42.5,
            }
        }

    def get_registry_entries(self) -> list[dict[str, Any]]:
        return [{"id": "beta", "name": "Beta", "installed": False, "repository": "fiestaboard-plugin--beta"}]

    def get_update_status(self) -> dict[str, bool]:
        return dict(self.update_status)

    def get_update_blocked_reasons(self) -> dict[str, str]:
        return {"blocked_plugin": "the incoming manifest needs a newer FiestaBoard core"}

    def get_manifest(self, plugin_id: str) -> Any:
        return self.manifests.get(plugin_id)

    def get_plugin(self, plugin_id: str) -> Any:
        return self.plugins.get(plugin_id)

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        return {"api_key": REAL_SECRET} if plugin_id == "alpha" else None

    def is_enabled(self, plugin_id: str) -> bool:
        return self.enabled.get(plugin_id, False)

    def fetch_plugin_data(self, plugin_id: str) -> Any:
        return self.fetch_result

    def get_plugin_options(self, plugin_id: str, options_id: str, request: Any, draft_config: Any = None) -> Any:
        from src.plugins.base import Option, OptionsResult

        return OptionsResult(options=[Option(value="AAPL", label="Apple")])

    # -- instances ----------------------------------------------------------
    def parse_instance_key(self, plugin_id: str) -> tuple[str, str | None]:
        base, _, label = plugin_id.partition(":")
        return base, (label or None)

    def make_instance_key(self, base_id: str, label: str) -> str:
        return f"{base_id}:{label}"

    def list_instances(self, base_id: str) -> list[dict[str, Any]]:
        return [{"label": "work", "enabled": False}] if base_id == "alpha" else []

    def create_instance(self, base_id: str, label: str) -> list[str]:
        return [] if label != "bad label" else ["Invalid instance label"]

    def delete_instance(self, base_id: str, label: str) -> list[str]:
        key = self.make_instance_key(base_id, label)
        return [] if key in self.plugins else [f"Instance not found: {key}"]

    def apply_stored_config(self, compound_key: str, stored: dict[str, Any]) -> list[str]:
        return []

    # -- mutation surface ---------------------------------------------------
    def set_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> list[str]:
        # Snapshot: the endpoint hands the *same dict object* down the chain
        # and un-masks it in place, so a call-args assertion would inspect the
        # already-repaired dict and pass no matter what.
        self.applied.append(copy.deepcopy(config))
        return list(self.config_errors)

    def enable_plugin(self, plugin_id: str) -> bool:
        return self.enable_ok

    def disable_plugin(self, plugin_id: str) -> bool:
        return True

    # -- install / update surface -------------------------------------------
    def install_from_registry(self, plugin_id: str) -> list[str]:
        return [] if plugin_id == "beta" else [f"Plugin '{plugin_id}' not found in the registry"]

    def install_from_git(self, repository: str, plugin_id: str | None = None, branch: str = "") -> list[str]:
        return []

    def uninstall_external_plugin(self, plugin_id: str) -> list[str]:
        return [] if plugin_id == "ext_plugin" else [f"Plugin '{plugin_id}' is a built-in plugin"]

    def check_for_updates(self) -> dict[str, bool]:
        return {"ext_plugin": True, "quiet_plugin": False}

    def get_plugin_source(self, plugin_id: str) -> Any:
        return self.sources.get(plugin_id)

    def clear_update_status(self, plugin_id: str) -> None:
        self.update_status.pop(plugin_id, None)


class _ContractConfigManager:
    """ConfigManager stub with the same masking contract as the real one."""

    SENSITIVE = {"api_key"}

    def __init__(self) -> None:
        self.configs: dict[str, dict[str, Any]] = {
            "alpha": {"enabled": True, "api_key": REAL_SECRET, "location": "New York, NY"},
        }
        self.removed: set[str] = set()

    def get_plugin_config(self, plugin_id: str, include_env_overrides: bool = True) -> dict[str, Any] | None:
        config = self.configs.get(plugin_id)
        return dict(config) if config else None

    def get_plugin_env_overrides(self, plugin_id: str) -> dict[str, Any]:
        return {}

    def set_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> None:
        self.configs[plugin_id] = dict(config)

    def enable_plugin(self, plugin_id: str) -> None:
        self.configs.setdefault(plugin_id, {})["enabled"] = True

    def disable_plugin(self, plugin_id: str) -> None:
        self.configs.setdefault(plugin_id, {})["enabled"] = False

    def delete_plugin_config(self, plugin_id: str) -> None:
        self.configs.pop(plugin_id, None)

    def mark_plugin_removed(self, plugin_id: str) -> None:
        self.removed.add(plugin_id)

    def clear_plugin_removed(self, plugin_id: str) -> None:
        self.removed.discard(plugin_id)

    def _mask_sensitive(self, obj: Any, path: str = "") -> Any:
        if isinstance(obj, dict):
            return {
                key: (MASK if key in self.SENSITIVE and isinstance(value, str) else self._mask_sensitive(value))
                for key, value in obj.items()
            }
        return obj


@pytest.fixture
def registry() -> _ContractRegistry:
    return _ContractRegistry()


@pytest.fixture
def config_manager() -> _ContractConfigManager:
    return _ContractConfigManager()


@pytest.fixture
def page_service():
    demo_page = SimpleNamespace(
        id="demo-page-1",
        model_dump=lambda: {"id": "demo-page-1", "name": "Alpha Demo", "type": "template"},
    )
    return SimpleNamespace(
        get_demo_page=lambda plugin_id, device_type=None: None,
        create_demo_page=lambda plugin_id, schema: (demo_page, False),
    )


@pytest.fixture
def client(_isolated_data_dir, registry, config_manager, page_service):
    """TestClient with the whole plugin collaborator set stubbed."""
    from src.api_server import app

    with (
        patch("src.plugins.routes.PLUGIN_SYSTEM_AVAILABLE", True),
        patch("src.plugins.routes.get_plugin_registry", new=lambda: registry),
        patch("src.plugins.routes.get_config_manager", new=lambda: config_manager),
        patch("src.plugins.routes.reset_display_service", new=Mock()),
        patch("src.plugins.routes.reset_template_engine", new=Mock()),
        patch("src.plugins.routes.get_page_service", new=lambda: page_service),
        patch("src.plugins.options_runtime._PLUGIN_OPTIONS_CACHE", new={}),
        patch("src.plugins.options_runtime._plugin_options_last_refresh", new={}),
    ):
        yield TestClient(app, raise_server_exceptions=False)


# ── GET /plugins ────────────────────────────────────────────────────────────


class TestListPlugins:
    def test_lists_every_plugin_with_its_id_name_and_enabled_flag(self, client):
        body = client.get("/plugins").json()

        assert [p["id"] for p in body["plugins"]] == ["alpha", "ext_plugin"]
        assert [p["name"] for p in body["plugins"]] == ["Alpha", "Ext Plugin"]
        assert [p["enabled"] for p in body["plugins"]] == [True, False]

    def test_totals_count_plugins_and_enabled_plugins_separately(self, client):
        body = client.get("/plugins").json()

        assert body["total"] == 2
        assert body["enabled_count"] == 1

    def test_a_configured_plugin_carries_its_config_masked(self, client):
        body = client.get("/plugins").json()

        alpha = next(p for p in body["plugins"] if p["id"] == "alpha")
        assert alpha["configured"] is True
        assert alpha["config"]["api_key"] == MASK
        assert alpha["config"]["location"] == "New York, NY"
        assert REAL_SECRET not in json.dumps(body)

    def test_an_unconfigured_plugin_reports_configured_false_and_an_empty_config(self, client):
        body = client.get("/plugins").json()

        ext = next(p for p in body["plugins"] if p["id"] == "ext_plugin")
        assert ext["configured"] is False
        assert ext["config"] == {}

    def test_503_when_the_plugin_system_failed_to_import(self, client):
        with patch("src.plugins.routes.PLUGIN_SYSTEM_AVAILABLE", False):
            response = client.get("/plugins")

        assert response.status_code == 503
        assert response.json()["detail"] == "Plugin system is not available."


# ── GET /plugins/variables/all ──────────────────────────────────────────────


class TestAllVariables:
    def test_returns_the_registry_variables_and_max_lengths(self, client):
        body = client.get("/plugins/variables/all").json()

        assert body["variables"] == {"alpha": {"value": {"description": "A value", "example": "X"}}}
        assert body["max_lengths"] == {"alpha": {"value": 10}}
        assert body["plugin_system_enabled"] is True


# ── GET /plugins/errors ─────────────────────────────────────────────────────


class TestPluginErrors:
    def test_reports_load_errors_keyed_by_plugin_id(self, client):
        body = client.get("/plugins/errors").json()

        assert body["errors"] == {"broken_plugin": ["ImportError: contract fixture"]}

    def test_reports_the_fetch_circuit_breakers_holding_plugins_back(self, client):
        """Run-time failures, not just load-time ones (new in this slice).

        ``registry.get_fetch_breaker_status()`` shipped with the pool-
        starvation fix (#1884) and nothing exposed it, so a plugin could sit
        quarantined for minutes while the UI showed only stale variables.
        """
        body = client.get("/plugins/errors").json()

        assert body["fetch_breakers"] == {
            "slow_plugin": {
                "consecutive_timeouts": 3,
                "quarantined": True,
                "cooldown_remaining_seconds": 42.5,
            }
        }


# ── GET /plugins/registry ───────────────────────────────────────────────────


class TestRegistryListing:
    def test_returns_the_curated_entries_with_their_install_state(self, client):
        body = client.get("/plugins/registry").json()

        entry = body["entries"][0]
        assert entry["id"] == "beta"
        assert entry["name"] == "Beta"
        assert entry["installed"] is False
        assert entry["repository"] == "fiestaboard-plugin--beta"
        # Always-present, never sometimes-absent: RegistryEntry declares the
        # whole key set with defaults, so the marketplace card does not have
        # to guess whether a missing `teaser` means "none" or "old payload".
        assert entry["teaser"] == ""
        assert entry["previews"] == []


# ── GET /plugins/updates ────────────────────────────────────────────────────


class TestUpdateStatus:
    def test_reports_which_plugins_have_updates_and_which_are_blocked(self, client):
        body = client.get("/plugins/updates").json()

        assert body["updates"] == {"ext_plugin": True, "quiet_plugin": False}
        assert body["blocked"] == {"blocked_plugin": "the incoming manifest needs a newer FiestaBoard core"}


# ── GET /plugins/{plugin_id} ────────────────────────────────────────────────


class TestPluginDetail:
    def test_carries_the_manifest_identity_fields_by_value(self, client):
        body = client.get("/plugins/alpha").json()

        assert body["id"] == "alpha"
        assert body["name"] == "Alpha"
        assert body["version"] == "1.0.0"
        assert body["author"] == "Contract Fixtures"
        assert body["category"] == "utility"
        assert body["plugin_type"] == "data"
        assert body["enabled"] is True

    def test_config_is_masked_and_the_stored_secret_never_appears(self, client):
        body = client.get("/plugins/alpha").json()

        assert body["config"]["api_key"] == MASK
        assert body["config"]["location"] == "New York, NY"
        assert REAL_SECRET not in json.dumps(body)

    def test_reports_the_demo_template_and_instance_topology(self, client):
        body = client.get("/plugins/alpha").json()

        assert body["has_demo"] is True
        assert body["demo_page_id"] is None
        assert body["base_plugin_id"] == "alpha"
        assert body["instance_label"] is None
        assert body["instances"] == [{"label": "work", "key": None, "enabled": False, "has_config": False}]

    def test_404_names_the_missing_plugin(self, client):
        response = client.get("/plugins/missing")

        assert response.status_code == 404
        assert response.json()["detail"] == "Plugin not found: missing"


# ── GET /plugins/{plugin_id}/manifest ───────────────────────────────────────


class TestPluginManifest:
    def test_returns_the_raw_manifest(self, client):
        body = client.get("/plugins/alpha/manifest").json()

        assert body["variables"] == {"value": {"description": "A value", "example": "X"}}

    def test_404_names_the_missing_plugin(self, client):
        response = client.get("/plugins/missing/manifest")

        assert response.status_code == 404
        assert response.json()["detail"] == "Plugin not found: missing"


# ── PUT /plugins/{plugin_id}/config ─────────────────────────────────────────


class TestUpdateConfig:
    def test_echoes_the_stored_config_back_masked(self, client):
        response = client.put(
            "/plugins/alpha/config",
            json={"config": {"api_key": "brand-new-key", "location": "London, UK"}},
        )

        assert response.status_code == 200
        assert response.json()["config"]["api_key"] == MASK
        assert response.json()["config"]["location"] == "London, UK"

    def test_a_real_new_key_reaches_the_live_plugin_and_the_store(self, client, registry, config_manager):
        client.put("/plugins/alpha/config", json={"config": {"api_key": "brand-new-key"}})

        assert registry.applied[-1]["api_key"] == "brand-new-key"
        assert config_manager.configs["alpha"]["api_key"] == "brand-new-key"

    def test_404_names_the_missing_plugin(self, client):
        response = client.put("/plugins/missing/config", json={"config": {}})

        assert response.status_code == 404
        assert response.json()["detail"] == "Plugin not found: missing"

    def test_schema_validation_failures_are_reported_per_field(self, client, registry):
        registry.config_errors = ["api_key: does not match the schema"]

        response = client.put("/plugins/alpha/config", json={"config": {"api_key": 5}})

        assert response.status_code == 400
        assert response.json()["detail"]["errors"] == ["api_key: does not match the schema"]
        # A dict detail must carry a message key — an errors-only body is the
        # anti-pattern API_CONVENTIONS.md bans.
        assert response.json()["detail"]["message"] == "Configuration for 'alpha' failed validation."


# ── The masking round-trip (the highest-stakes contract here) ───────────────


@pytest.fixture
def real_config(tmp_path, monkeypatch):
    """A real ConfigManager on a real file, holding a real stored secret.

    The disk assertions below are about what actually gets persisted, not
    about a mock's call log. CI's platform job exports ``WEATHER_API_KEY``
    (and friends), so every override this fixture does not set itself is
    deleted first — otherwise "the stored value survived" would be indis-
    tinguishable from "the ambient env value was written".
    """
    from src.config_manager import ENV_PLUGIN_OVERRIDES

    for env_var in ENV_PLUGIN_OVERRIDES:
        monkeypatch.delenv(env_var, raising=False)

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"board": {}, "features": {}, "general": {}, "plugins": {}}))
    cm = ConfigManager(config_path=str(config_path))
    cm.set_plugin_config("weather", {"enabled": True, "api_key": REAL_SECRET, "location": "New York, NY"})
    return cm


@pytest.fixture
def mask_client(_isolated_data_dir, real_config, registry, page_service):
    from src.api_server import app

    with (
        patch("src.plugins.routes.PLUGIN_SYSTEM_AVAILABLE", True),
        patch("src.plugins.routes.get_plugin_registry", new=lambda: registry),
        patch("src.plugins.get_plugin_registry", new=lambda: registry),
        patch("src.plugins.routes.get_config_manager", new=lambda: real_config),
        patch("src.plugins.routes.reset_display_service", new=Mock()),
        patch("src.plugins.routes.reset_template_engine", new=Mock()),
        patch("src.plugins.routes.get_page_service", new=lambda: page_service),
    ):
        registry.plugins["weather"] = Mock()
        registry.manifests["weather"] = registry.manifests["alpha"]
        registry.enabled["weather"] = True
        yield TestClient(app, raise_server_exceptions=False)


def _stored(cm: ConfigManager, plugin_id: str) -> dict[str, Any]:
    """What is actually on disk, with no env overlay."""
    return cm.get_plugin_config(plugin_id, include_env_overrides=False) or {}


class TestMaskedSecretRoundTrip:
    """A ``"***"`` posted back must resolve to the STORED secret. Always."""

    def test_the_sentinel_is_never_persisted_as_the_literal_mask(self, mask_client, real_config):
        response = mask_client.put(
            "/plugins/weather/config",
            json={"config": {"enabled": True, "api_key": MASK, "location": "Chicago, IL"}},
        )

        assert response.status_code == 200
        assert _stored(real_config, "weather")["api_key"] == REAL_SECRET
        assert _stored(real_config, "weather")["api_key"] != MASK

    def test_the_sentinel_never_reaches_the_live_plugin(self, mask_client, registry):
        mask_client.put(
            "/plugins/weather/config",
            json={"config": {"enabled": True, "api_key": MASK, "location": "Chicago, IL"}},
        )

        assert registry.applied[-1]["api_key"] == REAL_SECRET

    def test_the_rest_of_the_payload_still_saves(self, mask_client, real_config):
        mask_client.put(
            "/plugins/weather/config",
            json={"config": {"enabled": True, "api_key": MASK, "location": "Chicago, IL"}},
        )

        assert _stored(real_config, "weather")["location"] == "Chicago, IL"

    def test_a_genuinely_new_secret_still_replaces_the_stored_one(self, mask_client, real_config):
        mask_client.put(
            "/plugins/weather/config",
            json={"config": {"enabled": True, "api_key": "rotated-key", "location": "Chicago, IL"}},
        )

        assert _stored(real_config, "weather")["api_key"] == "rotated-key"


class TestEnvOverrideRoundTrip:
    """An env override steers the LIVE plugin and never touches the file."""

    # The override is set in each test body, not in a fixture: ``real_config``
    # deletes every ENV_PLUGIN_OVERRIDES variable so an ambient CI value cannot
    # masquerade as a stored one, and a class-level autouse fixture would run
    # *before* it and be deleted again.
    ENV_VALUE = "key-from-the-environment"

    def test_the_detail_endpoint_serves_the_stored_config_not_the_env_value(self, mask_client, monkeypatch):
        monkeypatch.setenv("WEATHER_API_KEY", self.ENV_VALUE)

        body = mask_client.get("/plugins/weather").json()

        # Masked, so neither value is visible — but the point is that the
        # env value is not what would come back in the next save.
        assert body["config"]["api_key"] == MASK
        assert self.ENV_VALUE not in json.dumps(body)

    def test_a_non_secret_env_override_is_not_baked_into_the_form(self, mask_client, monkeypatch):
        """The masked keys hide this one, so it needs its own unmasked witness.

        ``api_key`` is masked on the way out either way, so serving the
        env-overlaid config instead of the stored one is invisible on that
        field — a mutation that swaps ``include_env_overrides=False`` for the
        default passes every other assertion in this class. ``location`` is
        env-overridable and *not* sensitive, so it is where the difference
        shows: if the overlay were served, the form would show the env value,
        the user would save it back, and an env-supplied setting would be
        frozen into config.json permanently (#1864 review).
        """
        monkeypatch.setenv("WEATHER_LOCATION", "Reykjavik, IS")

        body = mask_client.get("/plugins/weather").json()

        assert body["config"]["location"] == "New York, NY"
        assert body["env_overridden_keys"] == ["location"]

    def test_env_overridden_keys_names_exactly_the_env_controlled_keys(self, mask_client, monkeypatch):
        monkeypatch.setenv("WEATHER_API_KEY", self.ENV_VALUE)

        body = mask_client.get("/plugins/weather").json()

        assert body["env_overridden_keys"] == ["api_key"]

    def test_saving_the_masked_form_persists_the_stored_secret_not_the_env_value(
        self, mask_client, real_config, monkeypatch
    ):
        monkeypatch.setenv("WEATHER_API_KEY", self.ENV_VALUE)

        mask_client.put(
            "/plugins/weather/config",
            json={"config": {"enabled": True, "api_key": MASK, "location": "Chicago, IL"}},
        )

        assert _stored(real_config, "weather")["api_key"] == REAL_SECRET
        assert _stored(real_config, "weather")["api_key"] != self.ENV_VALUE

    def test_the_live_plugin_config_keeps_the_env_value_after_the_save(self, mask_client, registry, monkeypatch):
        monkeypatch.setenv("WEATHER_API_KEY", self.ENV_VALUE)

        mask_client.put(
            "/plugins/weather/config",
            json={"config": {"enabled": True, "api_key": MASK, "location": "Chicago, IL"}},
        )

        # Last thing handed to the registry is the env-overlaid read: a save
        # must not kill a working env-supplied credential until restart.
        assert registry.applied[-1]["api_key"] == self.ENV_VALUE

    def test_no_env_override_means_no_env_overridden_keys(self, mask_client):
        body = mask_client.get("/plugins/weather").json()

        assert body["env_overridden_keys"] == []


# ── POST /plugins/{plugin_id}/enable and /disable ───────────────────────────


class TestEnableDisable:
    def test_enable_reports_the_plugin_enabled(self, client):
        response = client.post("/plugins/alpha/enable")

        assert response.status_code == 200
        assert response.json()["plugin_id"] == "alpha"
        assert response.json()["enabled"] is True

    def test_enable_persists_the_flag(self, client, config_manager):
        client.post("/plugins/alpha/enable")

        assert config_manager.configs["alpha"]["enabled"] is True

    def test_enable_404s_for_a_missing_plugin(self, client):
        response = client.post("/plugins/missing/enable")

        assert response.status_code == 404
        assert response.json()["detail"] == "Plugin not found: missing"

    def test_a_registry_refusal_is_a_400_naming_the_plugin(self, client, registry):
        registry.enable_ok = False

        response = client.post("/plugins/alpha/enable")

        assert response.status_code == 400
        assert response.json()["detail"] == "Failed to enable plugin: alpha"

    def test_disable_reports_the_plugin_disabled(self, client, config_manager):
        response = client.post("/plugins/alpha/disable")

        assert response.status_code == 200
        assert response.json()["enabled"] is False
        assert config_manager.configs["alpha"]["enabled"] is False


# ── GET /plugins/{plugin_id}/data ───────────────────────────────────────────


class TestPluginData:
    def test_returns_the_fetched_data_and_formatted_lines(self, client):
        body = client.get("/plugins/alpha/data").json()

        assert body["plugin_id"] == "alpha"
        assert body["available"] is True
        assert body["data"] == {"value": 42}
        assert body["formatted_lines"] == ["ALPHA 42"]
        assert body["error"] is None

    def test_404_for_a_plugin_that_is_not_installed(self, client):
        response = client.get("/plugins/missing/data")

        assert response.status_code == 404
        assert response.json()["detail"] == "Plugin not found: missing"

    def test_400_for_an_installed_but_disabled_plugin(self, client, registry):
        registry.enabled["alpha"] = False

        response = client.get("/plugins/alpha/data")

        assert response.status_code == 400
        assert response.json()["detail"] == "Plugin not enabled: alpha"

    def test_503_carries_the_plugin_reason_when_data_is_unavailable(self, client, registry):
        registry.fetch_result = SimpleNamespace(
            available=False, data=None, formatted_lines=None, error="not configured"
        )

        response = client.get("/plugins/alpha/data")

        assert response.status_code == 503
        assert response.json()["detail"] == "not configured"


# ── GET /plugins/{plugin_id}/variables ──────────────────────────────────────


class TestPluginVariables:
    def test_returns_the_variables_max_lengths_and_colour_rules_schema(self, client):
        body = client.get("/plugins/alpha/variables").json()

        assert body["plugin_id"] == "alpha"
        assert body["variables"] == {"value": {"description": "A value", "example": "X"}}
        assert body["max_lengths"] == {"value": 10}
        assert body["color_rules_schema"] == {}


# ── POST /plugins/{plugin_id}/options/{options_id} ──────────────────────────


class TestPluginOptions:
    def test_returns_the_providers_options_by_value(self, client):
        body = client.post("/plugins/alpha/options/symbols", json={"query": "AAP"}).json()

        assert body["plugin_id"] == "alpha"
        assert body["options_id"] == "symbols"
        assert body["options"] == [
            {
                "value": "AAPL",
                "label": "Apple",
                "description": None,
                "group": None,
                "preview": None,
                "disabled": False,
                "meta": None,
            }
        ]
        assert body["error"] is None

    def test_an_undeclared_provider_is_a_400_naming_it(self, client):
        response = client.post("/plugins/alpha/options/not_declared", json={})

        assert response.status_code == 400
        assert response.json()["detail"] == "Plugin 'alpha' does not declare options provider 'not_declared'"


# ── /plugins/{plugin_id}/demo-page ──────────────────────────────────────────


class TestDemoPage:
    def test_get_reports_no_page_yet_but_a_template_for_this_device(self, client):
        body = client.get("/plugins/alpha/demo-page").json()

        assert body["exists"] is False
        assert body["page_id"] is None
        assert body["has_demo_template"] is True

    def test_get_reports_no_template_for_a_plugin_without_a_demo(self, client):
        body = client.get("/plugins/norecv/demo-page").json()

        assert body == {"exists": False, "page_id": None, "has_demo_template": False}

    def test_create_returns_the_created_page(self, client):
        response = client.post("/plugins/alpha/demo-page?device_type=flagship")

        assert response.status_code == 201
        assert response.json()["page"]["id"] == "demo-page-1"
        assert response.json()["page"]["name"] == "Alpha Demo"
        assert response.json()["recreated"] is False

    def test_create_400s_for_a_plugin_that_ships_no_demo(self, client):
        response = client.post("/plugins/norecv/demo-page")

        assert response.status_code == 400
        assert response.json()["detail"] == "Plugin 'norecv' does not include a demo page template."


# ── /plugins/{plugin_id}/instances ──────────────────────────────────────────


class TestInstances:
    def test_list_returns_the_instances_of_the_base_plugin(self, client):
        body = client.get("/plugins/alpha/instances").json()

        assert body["plugin_id"] == "alpha"
        assert body["instances"] == [{"label": "work", "key": None, "enabled": False, "has_config": False}]
        assert body["total"] == 1

    def test_create_reports_the_normalized_label_and_compound_key(self, client):
        response = client.post("/plugins/alpha/instances", json={"label": "office"})

        assert response.status_code == 201
        body = response.json()
        assert body["plugin_id"] == "alpha"
        assert body["instance_label"] == "office"
        assert body["instance_key"] == "alpha:office"

    def test_create_seeds_a_disabled_config_for_the_new_instance(self, client, config_manager):
        client.post("/plugins/alpha/instances", json={"label": "office"})

        assert config_manager.configs["alpha:office"] == {"enabled": False}

    def test_a_rejected_label_is_a_400_carrying_the_registry_reason(self, client):
        response = client.post("/plugins/alpha/instances", json={"label": "bad label"})

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid instance label"

    def test_delete_reports_the_key_it_removed(self, client):
        response = client.delete("/plugins/alpha/instances/work")

        assert response.status_code == 200
        assert response.json()["instance_key"] == "alpha:work"

    def test_delete_purges_the_config_and_tombstones_the_key(self, client, config_manager):
        config_manager.configs["alpha:work"] = {"enabled": True}

        client.delete("/plugins/alpha/instances/work")

        assert "alpha:work" not in config_manager.configs
        assert "alpha:work" in config_manager.removed

    def test_deleting_an_instance_that_does_not_exist_is_404(self, client):
        """DELIBERATE CONTRACT CHANGE (review finding 6, this PR).

        Was **400**, for the same reason as
        ``TestUninstall::test_uninstalling_a_plugin_that_does_not_exist_is_404``:
        the registry's "Instance not found" is an error string that became a
        ``PluginOperationRejected``. The sibling ``POST`` on this same path
        raises ``PluginNotFound``.
        """
        response = client.delete("/plugins/alpha/instances/nosuchlabel")

        assert response.status_code == 404
        assert response.json()["detail"] == "Instance not found: alpha:nosuchlabel"


# ── POST /plugins/{plugin_id}/receive ───────────────────────────────────────


class TestReceivePayload:
    def test_a_supported_plugin_accepts_the_payload(self, client, registry):
        registry.plugins["alpha"].receive_payload = Mock(return_value=None)

        response = client.post("/plugins/alpha/receive", json={"hello": "world"})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "plugin_id": "alpha"}
        assert registry.plugins["alpha"].receive_payload.call_args[0][0] == {"hello": "world"}

    def test_405_when_the_plugin_does_not_implement_receive(self, client, registry):
        registry.plugins["alpha"].receive_payload = Mock(side_effect=NotImplementedError())

        response = client.post("/plugins/alpha/receive", json={})

        assert response.status_code == 405
        assert response.json()["detail"] == "Plugin 'alpha' does not support receive"

    def test_403_when_the_plugin_rejects_the_signature(self, client, registry):
        registry.plugins["alpha"].receive_payload = Mock(side_effect=PermissionError("bad signature"))

        response = client.post("/plugins/alpha/receive", json={})

        assert response.status_code == 403
        assert response.json()["detail"] == "bad signature"

    def test_400_for_a_body_that_is_not_json(self, client):
        response = client.post("/plugins/alpha/receive", content=b"not json")

        assert response.status_code == 400
        assert response.json()["detail"] == "Request body must be valid JSON"

    def test_400_for_a_disabled_plugin(self, client, registry):
        registry.enabled["alpha"] = False

        response = client.post("/plugins/alpha/receive", json={})

        assert response.status_code == 400
        assert response.json()["detail"] == "Plugin not enabled: alpha"


# ── Install / uninstall / update ────────────────────────────────────────────


class TestInstall:
    def test_registry_install_reports_the_installed_plugin_id(self, client):
        response = client.post("/plugins/registry/beta/install")

        assert response.status_code == 201
        assert response.json()["plugin_id"] == "beta"

    def test_a_registry_install_failure_is_a_400_carrying_the_reason(self, client):
        response = client.post("/plugins/registry/nope/install")

        assert response.status_code == 400
        assert response.json()["detail"] == "Plugin 'nope' not found in the registry"

    def test_a_git_install_derives_the_plugin_id_from_the_repo_name(self, client):
        response = client.post(
            "/plugins/install",
            json={"repository": "https://github.com/example/fiestaboard-plugin--gamma"},
        )

        assert response.status_code == 201
        assert response.json()["plugin_id"] == "gamma"

    def test_a_malformed_branch_is_rejected_before_any_clone(self, client):
        response = client.post(
            "/plugins/install",
            json={"repository": "https://github.com/example/repo", "branch": "--upload-pack=evil"},
        )

        assert response.status_code == 400

    def test_a_malformed_plugin_id_is_rejected(self, client):
        response = client.post(
            "/plugins/install",
            json={"repository": "https://github.com/example/repo", "plugin_id": "Bad-Id"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "plugin_id may contain only lowercase letters, digits, and underscores"


class TestUninstall:
    def test_uninstalling_an_external_plugin_reports_its_id(self, client):
        response = client.delete("/plugins/ext_plugin/uninstall")

        assert response.status_code == 200
        assert response.json()["plugin_id"] == "ext_plugin"

    def test_a_builtin_refusal_is_a_400_carrying_the_reason(self, client):
        response = client.delete("/plugins/alpha/uninstall")

        assert response.status_code == 400
        assert response.json()["detail"] == "Plugin 'alpha' is a built-in plugin"

    def test_uninstalling_a_plugin_that_does_not_exist_is_404(self, client):
        """DELIBERATE CONTRACT CHANGE (review finding 6, this PR).

        Was **400** with the literal detail "Plugin not found: ghost": the
        registry reports the missing case as an error *string*, which
        ``PluginService`` wrapped in ``PluginOperationRejected`` -> 400. The
        route declares ``errors(400, 404, 503)``, so the declared 404 was
        unreachable, and ``POST /plugins/{id}/instances`` already raised
        ``PluginNotFound`` for exactly this condition — the create/delete
        asymmetry was the tell.
        """
        response = client.delete("/plugins/ghost/uninstall")

        assert response.status_code == 404
        assert response.json()["detail"] == "Plugin not found: ghost"


class TestUpdates:
    def test_the_update_check_reports_how_many_were_checked_and_which_have_updates(self, client):
        body = client.post("/plugins/updates/check").json()

        assert body["checked"] == 2
        assert body["updates_available"] == ["ext_plugin"]

    def test_updating_a_plugin_with_no_source_404s(self, client):
        response = client.post("/plugins/nosource/update")

        assert response.status_code == 404
        assert response.json()["detail"] == "Plugin 'nosource' not found."

    def test_updating_a_builtin_is_a_400_saying_so(self, client):
        response = client.post("/plugins/alpha/update")

        assert response.status_code == 400
        assert response.json()["detail"] == "Plugin 'alpha' is a built-in plugin and cannot be updated this way."

    def test_apply_all_with_nothing_pending_says_so(self, client, registry):
        registry.update_status = {"ext_plugin": False}

        body = client.post("/plugins/updates/apply").json()

        assert body["updated"] == []
        assert body["failed"] == {}
        assert body["message"] == "No updates available."
