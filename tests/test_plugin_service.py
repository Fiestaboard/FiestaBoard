"""Unit tests for :class:`src.plugins.service.PluginService` (issue #1757).

The service owns the mutate → persist → reset-display → reset-template-engine
orchestration that used to be copy-pasted across five REST handlers, plus the
only sanctioned reaches into ``ConfigManager._mask_sensitive`` and
``PluginRegistry._update_status``. These tests pin the sequence and the error
contract; the HTTP-visible behavior on top is pinned by the response-shape
goldens (tests/test_response_shape_goldens.py) and the lifecycle round-trip
suite.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from src.plugins.service import PluginService, sanitize_optional_plugin_id


class _Recorder:
    """Records the order of orchestration steps across collaborators."""

    def __init__(self) -> None:
        self.steps: list[str] = []


def _service(recorder: _Recorder, *, config_errors: list[str] | None = None) -> PluginService:
    registry = Mock()
    registry.get_plugin.return_value = object()
    registry.set_plugin_config.side_effect = lambda pid, cfg: (
        recorder.steps.append("validate"),
        list(config_errors or []),
    )[1]
    registry.enable_plugin.side_effect = lambda pid: (recorder.steps.append("registry_enable"), True)[1]
    registry.disable_plugin.side_effect = lambda pid: (recorder.steps.append("registry_disable"), True)[1]
    registry.parse_instance_key.side_effect = lambda pid: (pid.partition(":")[0], pid.partition(":")[2] or None)
    registry.make_instance_key.side_effect = lambda base, label: f"{base}:{label}"
    registry.create_instance.return_value = []
    registry.delete_instance.return_value = []

    config_manager = Mock()
    config_manager.get_plugin_config.return_value = {"api_key": "test_key_123"}
    config_manager.set_plugin_config.side_effect = lambda pid, cfg: recorder.steps.append("persist")
    config_manager.enable_plugin.side_effect = lambda pid: recorder.steps.append("persist")
    config_manager.disable_plugin.side_effect = lambda pid: recorder.steps.append("persist")
    config_manager.delete_plugin_config.side_effect = lambda pid: recorder.steps.append("persist")
    config_manager._mask_sensitive.side_effect = lambda cfg: dict.fromkeys(cfg, "***")

    return PluginService(
        registry=registry,
        config_manager=config_manager,
        reset_display=lambda: recorder.steps.append("reset_display"),
        reset_template=lambda: recorder.steps.append("reset_template"),
    )


ORCHESTRATION_TAIL = ["persist", "reset_display", "reset_template"]


def test_update_plugin_config_runs_validate_persist_reset_in_order():
    rec = _Recorder()
    svc = _service(rec)

    masked = svc.update_plugin_config("alpha", {"api_key": "new_key", "location": "NYC"})

    assert rec.steps == ["validate", *ORCHESTRATION_TAIL]
    assert masked == {"api_key": "***"}


def test_update_plugin_config_validation_failure_neither_persists_nor_resets():
    rec = _Recorder()
    svc = _service(rec, config_errors=["api_key: too short"])

    with pytest.raises(HTTPException) as exc_info:
        svc.update_plugin_config("alpha", {"api_key": "x"})

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"errors": ["api_key: too short"]}
    assert rec.steps == ["validate"], "a rejected config must not be saved or applied"


def test_update_plugin_config_unmasks_the_sentinel_before_validation():
    """A posted '***' must reach the registry as the stored secret (#1743)."""
    rec = _Recorder()
    svc = _service(rec)

    svc.update_plugin_config("alpha", {"api_key": "***"})

    seen = svc.registry.set_plugin_config.call_args[0][1]
    assert seen["api_key"] == "test_key_123"


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("enable_plugin", ("alpha",)),
        ("disable_plugin", ("alpha",)),
        ("delete_instance", ("alpha", "work")),
    ],
    ids=["enable", "disable", "delete_instance"],
)
def test_every_mutation_ends_with_the_same_reset_tail(method, args):
    rec = _Recorder()
    svc = _service(rec)

    getattr(svc, method)(*args)

    assert rec.steps[-2:] == ["reset_display", "reset_template"]
    assert "persist" in rec.steps


def test_create_instance_persists_then_resets():
    rec = _Recorder()
    svc = _service(rec)
    svc.config_manager.get_plugin_config.return_value = None  # fresh instance

    base_id, compound_key = svc.create_instance("alpha", "work")

    assert (base_id, compound_key) == ("alpha", "alpha:work")
    assert rec.steps == ORCHESTRATION_TAIL
    svc.config_manager.clear_plugin_removed.assert_called_once_with("alpha:work")


def test_unknown_plugin_is_a_404_for_config_enable_and_disable():
    rec = _Recorder()
    svc = _service(rec)
    svc.registry.get_plugin.return_value = None

    for call in (
        lambda: svc.update_plugin_config("missing", {}),
        lambda: svc.enable_plugin("missing"),
        lambda: svc.disable_plugin("missing"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            call()
        assert exc_info.value.status_code == 404


def test_mask_config_delegates_to_the_config_managers_masker():
    svc = _service(_Recorder())

    assert svc.mask_config({"api_key": "k", "location": "NYC"}) == {"api_key": "***", "location": "***"}
    assert svc.mask_config(None) == {}
    assert svc.mask_config({}) == {}


def test_clear_update_status_pops_the_registrys_cache():
    svc = _service(_Recorder())
    svc.registry._update_status = {"ext": True, "other": False}

    svc.clear_update_status("ext")
    svc.clear_update_status("never_there")  # must not raise

    assert svc.registry._update_status == {"other": False}


def test_bare_service_resolves_collaborators_from_canonical_homes():
    """``PluginService()`` — the MCP path — must resolve through
    ``src.plugins`` / ``src.config_manager``, never ``src.api_server``."""
    registry = Mock()
    config_manager = Mock()

    with (
        patch("src.plugins.get_plugin_registry", return_value=registry),
        patch("src.config_manager.get_config_manager", return_value=config_manager),
    ):
        svc = PluginService()
        assert svc.registry is registry
        assert svc.config_manager is config_manager


@pytest.mark.parametrize("bad", ["", "UPPER", "has-dash", "has space", "dot.dot"])
def test_sanitize_optional_plugin_id_rejects_invalid_ids(bad: str):
    with pytest.raises(HTTPException) as exc_info:
        sanitize_optional_plugin_id(bad)
    assert exc_info.value.status_code == 400


def test_sanitize_optional_plugin_id_accepts_none_and_valid_ids():
    assert sanitize_optional_plugin_id(None) is None
    assert sanitize_optional_plugin_id("my_plugin2") == "my_plugin2"


@pytest.mark.asyncio
async def test_install_from_registry_errors_become_a_400():
    svc = _service(_Recorder())
    svc.registry.install_from_registry = Mock(return_value=["Plugin 'nope' not found in the registry"])

    with pytest.raises(HTTPException) as exc_info:
        await svc.install_from_registry("nope")

    assert exc_info.value.status_code == 400
    assert "not found in the registry" in exc_info.value.detail


@pytest.mark.asyncio
async def test_install_from_git_derives_the_plugin_id_from_the_repo_name():
    svc = _service(_Recorder())
    svc.registry.install_from_git = Mock(return_value=[])

    pid = await svc.install_from_git("https://github.com/example/fiestaboard-plugin--my-ext.git")

    assert pid == "my_ext"


@pytest.mark.asyncio
async def test_install_from_git_rejects_a_bad_branch_before_touching_git():
    svc = _service(_Recorder())
    svc.registry.install_from_git = Mock(return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        await svc.install_from_git("https://github.com/example/fiestaboard-plugin--x.git", branch="bad branch")

    assert exc_info.value.status_code == 400
    svc.registry.install_from_git.assert_not_called()


def test_uninstall_purges_base_and_instance_configs():
    svc = _service(_Recorder())
    svc.registry.list_plugins = Mock(
        return_value=[
            {"id": "ext:home", "base_plugin_id": "ext", "instance_label": "home"},
            {"id": "other", "base_plugin_id": None, "instance_label": None},
        ]
    )
    svc.registry.uninstall_external_plugin = Mock(return_value=[])

    svc.uninstall("ext")

    deleted = [call.args[0] for call in svc.config_manager.delete_plugin_config.call_args_list]
    assert deleted == ["ext:home", "ext"]


@pytest.mark.asyncio
async def test_apply_update_missing_source_is_a_404_and_builtin_a_400():
    svc = _service(_Recorder())

    svc.registry.get_plugin_source = Mock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await svc.apply_update("missing")
    assert exc_info.value.status_code == 404

    svc.registry.get_plugin_source = Mock(return_value=Mock(source_type="builtin", local_path=None))
    with pytest.raises(HTTPException) as exc_info:
        await svc.apply_update("alpha")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_apply_all_updates_with_nothing_pending_is_a_no_op():
    svc = _service(_Recorder())
    svc.registry.get_update_status = Mock(return_value={"quiet": False})

    result = await svc.apply_all_updates()

    assert result == {"updated": [], "failed": {}, "message": "No updates available."}
