"""v11 release isolation, including clients shipped before the lane existed."""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.release.plan import plan_release
from scripts.release.pre_mode import PreJson, check_pre_mode_for_base

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("pre", [None, PreJson("pre", "beta"), PreJson("broken", "alpha")])
def test_v11_requires_alpha_pre_mode(pre):
    assert not check_pre_mode_for_base("v11", pre).ok


@pytest.mark.parametrize("mode,action", [("pre", "release"), ("exit", "skip")])
def test_v11_action(mode, action, tmp_path):
    import json

    (tmp_path / ".changeset").mkdir()
    (tmp_path / ".changeset/pre.json").write_text(json.dumps({"mode": mode, "tag": "alpha"}))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/release/pre_mode.py"), "v11-action"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"action={action}"


def test_v11_plan_uses_isolated_image_tags():
    plan = plan_release(branch="v11", version="11.0.0-alpha.0", release_exists=False)
    assert plan.release and plan.prerelease
    assert plan.image_tag == "v11-alpha-11.0.0-alpha.0"
    assert plan.moving_tag == "v11-alpha"
    assert plan.tag == "v11.0.0-alpha.0"


@pytest.mark.parametrize("version", ["11.0.0", "11.0.0-beta.0", "10.4.0-alpha.1", "11.1.0-alpha.0", "11.0.0-alpha.x"])
def test_v11_rejects_other_version_lines(version):
    with pytest.raises(ValueError, match="v11 would release"):
        plan_release(branch="v11", version=version, release_exists=False)


@pytest.mark.parametrize("branch,version,moving", [("main", "10.4.0", "latest"), ("alpha", "10.4.0-beta.0", "beta")])
def test_existing_lanes_keep_their_tags(branch, version, moving):
    plan = plan_release(branch=branch, version=version, release_exists=False)
    assert plan.image_tag == version
    assert plan.moving_tag == moving


def test_bootstrapped_v11_does_not_republish_existing_stable():
    assert not plan_release(branch="v11", version="10.3.3", release_exists=True).release


def test_prefixed_images_are_invisible_to_unmodified_beta_discovery(monkeypatch):
    from unittest.mock import Mock

    from src.system import update_service

    response = Mock()
    response.json.return_value = {
        "results": [{"name": tag} for tag in ["v11-alpha", "v11-alpha-11.0.0-alpha.0", "10.4.0-beta.2", "10.3.3"]]
    }
    monkeypatch.setattr(update_service.requests, "get", lambda *args, **kwargs: response)
    assert update_service._check_dockerhub_for_latest("beta") == "10.4.0-beta.2"
    assert update_service._check_dockerhub_for_latest("stable") == "10.3.3"


@pytest.mark.parametrize("returncode,stderr,expected", [(0, "", True), (1, "gh: Not Found (HTTP 404)", False)])
def test_v11_completion_uses_git_tag_not_public_release(monkeypatch, returncode, stderr, expected):
    from scripts.release import plan

    def run(*args):
        assert args == ("gh", "api", "repos/{owner}/{repo}/git/ref/tags/v11.0.0-alpha.0")
        return subprocess.CompletedProcess(args, returncode, "", stderr)

    monkeypatch.setattr(plan, "_run", run)
    assert plan.v11_tag_exists("v11.0.0-alpha.0") is expected


def test_tag_lookup_errors_cannot_trigger_republication(monkeypatch):
    from scripts.release import plan

    monkeypatch.setattr(plan, "_run", lambda *args: subprocess.CompletedProcess(args, 1, "", "HTTP 403"))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        plan.v11_tag_exists("v11.0.0-alpha.0")


@pytest.mark.parametrize("exists", [False, True])
def test_v11_cli_outputs_isolated_publish_plan(monkeypatch, capsys, exists):
    from scripts.release import plan

    monkeypatch.setattr(plan, "version_at", lambda ref: "11.0.0-alpha.0")
    monkeypatch.setattr(plan, "version_commit", lambda: "abc123")
    monkeypatch.setattr(plan, "v11_tag_exists", lambda tag: exists)
    monkeypatch.setattr(plan, "newest_stable_release", lambda: "10.3.3")
    monkeypatch.setattr(plan, "release_exists", lambda tag: pytest.fail("v11 must not query public Releases"))
    assert plan.main(["v11"]) == 0
    outputs = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    assert outputs["release"] == str(not exists).lower()
    assert outputs["release_sha"] == ("" if exists else "abc123")
    assert outputs["image_tag"] == "v11-alpha-11.0.0-alpha.0"
    assert outputs["moving_tag"] == "v11-alpha"


def test_manifest_step_publishes_only_planned_tags(tmp_path):
    import os

    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    step = next(s for s in workflow["jobs"]["merge"]["steps"] if s.get("name") == "Create manifest list and push")
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    docker.chmod(0o755)
    digest_dir = tmp_path / "digests"
    digest_dir.mkdir()
    (digest_dir / ("a" * 64)).touch()
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=digest_dir,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "VERSION": "v11-alpha-11.0.0-alpha.0",
            "MOVING": "v11-alpha",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    tags = [line for line in result.stdout.splitlines() if line.startswith("fiestaboard/fiestaboard:")]
    assert tags == ["fiestaboard/fiestaboard:v11-alpha-11.0.0-alpha.0", "fiestaboard/fiestaboard:v11-alpha"]


def test_v11_workflow_never_creates_public_release():
    import yaml

    jobs = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())["jobs"]
    assert jobs["release"]["if"] == "github.ref_name != 'v11'"
    assert jobs["v11-tag"]["if"] == "github.ref_name == 'v11'"
    assert set(jobs["v11-tag"]["needs"]) == {"version", "merge"}
    steps = {s.get("id"): s for s in jobs["version"]["steps"]}
    assert steps["v11"]["if"] == "github.ref_name == 'v11'"
    assert "steps.v11.outputs.action == 'release'" in steps["plan"]["if"]
    action = next(s for s in jobs["version"]["steps"] if s.get("uses", "").startswith("changesets/action@"))
    assert "steps.v11.outputs.action == 'release'" in action["if"]


@pytest.mark.asyncio
async def test_v11_update_now_refuses_before_sidecar_or_snapshot(monkeypatch):
    from src.system import update_service as service

    monkeypatch.setenv("VERSION", "11.0.0-alpha.0")
    monkeypatch.setattr(service, "_updater_token", lambda: pytest.fail("sidecar access"))
    with pytest.raises(service.SidecarError, match="manually"):
        await service.apply_update()


def test_v11_channel_switch_refuses_before_sidecar(monkeypatch):
    from src.system import update_service as service

    monkeypatch.setenv("VERSION", "11.0.0-alpha.0")
    monkeypatch.setattr(service, "_updater_version", lambda: pytest.fail("sidecar access"))
    for channel in ("stable", "beta"):
        with pytest.raises(service.SidecarError, match="manually"):
            service.switch_channel(channel)


@pytest.mark.parametrize("wanted", ["stable", "beta"])
def test_v11_restart_ignores_old_channel_preference(monkeypatch, wanted):
    from src.system import update_service as service

    monkeypatch.setenv("VERSION", "11.0.0-alpha.0")
    monkeypatch.setattr(service, "_system_update_state_load", lambda: {"channel": wanted})
    monkeypatch.setattr(service, "_managed_externally", lambda: pytest.fail("must stop before sidecar probing"))
    calls = []
    monkeypatch.setattr(service, "switch_channel", lambda channel: calls.append(channel))
    service.reassert_release_channel()
    assert calls == []
    assert "manually" in service.channel_switch_blocker()


@pytest.mark.asyncio
async def test_v11_update_check_does_not_discover_other_channels(monkeypatch):
    from src.system import update_service as service

    monkeypatch.setenv("VERSION", "11.0.0-alpha.0")

    async def fail(channel):
        pytest.fail("v11 must not discover beta or stable updates")

    monkeypatch.setattr(service, "_latest_for_channel", fail)
    result = await service._perform_update_check()
    assert not result.update_available
    assert "manually" in result.error
