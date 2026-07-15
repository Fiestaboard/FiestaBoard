"""Tests to validate docker-compose files have correct network configuration.

These tests parse the YAML compose files and verify:
- All services in dev compose share an explicit network.
- Healthchecks are present in production compose files.
- Port mappings are consistent.
- The Dockerfile's default (last) stage is the production runtime, so a
  target-less build (e.g. the published image) does not boot the dev
  supervisor config.
"""

import os
import re

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_compose(filename: str) -> dict:
    path = os.path.join(REPO_ROOT, filename)
    if not os.path.exists(path):
        pytest.skip(f"{filename} not found at {path} (not available in this environment)")
    with open(path) as fh:
        return yaml.safe_load(fh)


def _parse_dockerfile_stages(filename: str = "Dockerfile"):
    """Parse a Dockerfile into ordered build stages.

    Returns a list of dicts ``{"name", "base", "cmd"}`` in file order, where
    ``cmd`` is the raw text of the last exec-form ``CMD [...]`` line in that
    stage (or None). Only the JSON-array form is matched, so the shell-form
    ``CMD`` inside a ``HEALTHCHECK`` instruction is ignored.
    """
    path = os.path.join(REPO_ROOT, filename)
    if not os.path.exists(path):
        pytest.skip(f"{filename} not found at {path} (not available in this environment)")

    stages = []
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            m = re.match(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?\s*$", line, re.IGNORECASE)
            if m:
                stages.append({"name": m.group(2), "base": m.group(1), "cmd": None})
                continue
            if re.match(r"^CMD\s*\[", line, re.IGNORECASE) and stages:
                stages[-1]["cmd"] = line[3:].strip()
    return stages


def _resolve_cmd(stages, stage_name):
    """Resolve a stage's effective CMD, walking the FROM chain if unset."""
    by_name = {s["name"]: s for s in stages if s["name"]}
    seen = set()
    current = by_name.get(stage_name)
    while current and current["name"] not in seen:
        if current["cmd"] is not None:
            return current["cmd"]
        seen.add(current["name"])
        current = by_name.get(current["base"])
    return None


# ---------------------------------------------------------------------------
# docker-compose.dev.yml
# ---------------------------------------------------------------------------


class TestDevComposeNetwork:
    """Validate that docker-compose.dev.yml uses explicit networks."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.compose = _load_compose("docker-compose.dev.yml")

    def test_network_defined(self):
        """A named network must be defined at the top level."""
        networks = self.compose.get("networks", {})
        assert len(networks) > 0, "docker-compose.dev.yml should define at least one network"

    def test_all_services_on_shared_network(self):
        """Every service should explicitly reference the shared network."""
        networks = list(self.compose.get("networks", {}).keys())
        assert len(networks) > 0

        shared_net = networks[0]
        services = self.compose.get("services", {})

        for name, svc in services.items():
            svc_nets = svc.get("networks", [])
            assert shared_net in svc_nets, f"Service '{name}' is missing network '{shared_net}'"

    def test_mock_board_on_same_network_as_app(self):
        """The mock board must be on the same network as the main app."""
        services = self.compose.get("services", {})
        app_nets = set(services.get("fiestaboard", {}).get("networks", []))
        mock_nets = set(services.get("fiestaboard-mock-board", {}).get("networks", []))
        assert app_nets & mock_nets, "fiestaboard and fiestaboard-mock-board must share at least one network"

    def test_network_driver_is_bridge(self):
        """The defined network should use the bridge driver."""
        for net_name, net_cfg in self.compose.get("networks", {}).items():
            driver = (net_cfg or {}).get("driver", "bridge")
            assert driver == "bridge", f"Network '{net_name}' should use bridge driver"


# ---------------------------------------------------------------------------
# docker-compose.yml (production)
# ---------------------------------------------------------------------------


class TestProdCompose:
    """Validate docker-compose.yml (production) settings."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.compose = _load_compose("docker-compose.yml")

    def test_healthcheck_present(self):
        """Production service should have a healthcheck."""
        svc = self.compose["services"]["fiestaboard"]
        assert "healthcheck" in svc, "Production service is missing healthcheck"

    def test_healthcheck_test_command(self):
        """Healthcheck should hit the health endpoint."""
        hc = self.compose["services"]["fiestaboard"]["healthcheck"]
        test_cmd = " ".join(hc["test"]) if isinstance(hc["test"], list) else hc["test"]
        assert "/api/health" in test_cmd

    def test_port_mapping(self):
        """Host port 4420 should map to container port 3000."""
        ports = self.compose["services"]["fiestaboard"].get("ports", [])
        assert "4420:3000" in ports

    def test_build_target_is_runtime(self):
        """Production compose must pin the `runtime` stage explicitly."""
        build = self.compose["services"]["fiestaboard"].get("build", {})
        assert isinstance(build, dict), "Production build should specify an explicit target"
        assert build.get("target") == "runtime"


# ---------------------------------------------------------------------------
# Dockerfile default (last) stage — regression guard for #1377
# ---------------------------------------------------------------------------


class TestDockerfileDefaultStage:
    """A target-less build must produce the PRODUCTION image.

    BuildKit builds a Dockerfile's LAST stage when no `--target` is given.
    Several builds (the release workflow, some CI e2e jobs) omit `--target`,
    so the last stage must be production. When `runtime-dev` was last, the
    published `fiestaboard/fiestaboard:latest` image shipped with
    `CMD ["supervisord", "-c", "/app/supervisord-dev.conf"]` and looped
    spawning the `rr7` dev server on ARM64 (issue #1377).
    """

    @pytest.fixture(autouse=True)
    def load(self):
        self.stages = _parse_dockerfile_stages("Dockerfile")

    def test_last_stage_is_named_runtime(self):
        named = [s for s in self.stages if s["name"]]
        assert named, "Dockerfile should define named build stages"
        assert named[-1]["name"] == "runtime", (
            "The final Dockerfile stage must be the production `runtime` stage; "
            "otherwise a target-less build boots supervisord-dev.conf (issue #1377)"
        )

    def test_default_stage_uses_production_supervisor(self):
        named = [s for s in self.stages if s["name"]]
        last = named[-1]["name"]
        cmd = _resolve_cmd(self.stages, last)
        assert cmd is not None, f"Could not resolve CMD for final stage '{last}'"
        assert "supervisord.conf" in cmd
        assert "supervisord-dev.conf" not in cmd, (
            "The default build stage must not use the dev supervisor config (issue #1377)"
        )

    def test_dev_stage_still_available(self):
        """The dev stage must remain for docker-compose.dev.yml (target: runtime-dev)."""
        names = {s["name"] for s in self.stages if s["name"]}
        assert "runtime-dev" in names
        dev_cmd = _resolve_cmd(self.stages, "runtime-dev")
        assert dev_cmd is not None and "supervisord-dev.conf" in dev_cmd


# ---------------------------------------------------------------------------
# docker-compose.hub.yml
# ---------------------------------------------------------------------------


class TestHubCompose:
    """Validate docker-compose.hub.yml settings."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.compose = _load_compose("docker-compose.hub.yml")

    def test_healthcheck_present(self):
        svc = self.compose["services"]["fiestaboard"]
        assert "healthcheck" in svc

    def test_port_mapping(self):
        ports = self.compose["services"]["fiestaboard"].get("ports", [])
        assert "4420:3000" in ports


# ---------------------------------------------------------------------------
# docker-compose.prod.yml
# ---------------------------------------------------------------------------


class TestProdPrebuiltCompose:
    """Validate docker-compose.prod.yml settings."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.compose = _load_compose("docker-compose.prod.yml")

    def test_healthcheck_present(self):
        svc = self.compose["services"]["fiestaboard"]
        assert "healthcheck" in svc

    def test_port_mapping(self):
        ports = self.compose["services"]["fiestaboard"].get("ports", [])
        assert "4420:3000" in ports
