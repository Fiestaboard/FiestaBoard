"""Tests to validate docker-compose files have correct network configuration.

These tests parse the YAML compose files and verify:
- All services in dev compose share an explicit network.
- Healthchecks are present in production compose files.
- Port mappings are consistent.
"""

import os

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_compose(filename: str) -> dict:
    path = os.path.join(REPO_ROOT, filename)
    with open(path) as fh:
        return yaml.safe_load(fh)


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
            assert shared_net in svc_nets, (
                f"Service '{name}' is missing network '{shared_net}'"
            )

    def test_mock_board_on_same_network_as_app(self):
        """The mock board must be on the same network as the main app."""
        services = self.compose.get("services", {})
        app_nets = set(services.get("fiestaboard", {}).get("networks", []))
        mock_nets = set(services.get("fiestaboard-mock-board", {}).get("networks", []))
        assert app_nets & mock_nets, (
            "fiestaboard and fiestaboard-mock-board must share at least one network"
        )

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


# ---------------------------------------------------------------------------
# In-container monitoring (supervisord-monitoring.conf + configs)
# ---------------------------------------------------------------------------

class TestInContainerMonitoring:
    """Validate that the in-container monitoring config files are correct."""

    def test_supervisord_monitoring_conf_exists(self):
        """supervisord-monitoring.conf must exist in the repo root."""
        path = os.path.join(REPO_ROOT, "supervisord-monitoring.conf")
        assert os.path.isfile(path)

    def test_supervisord_monitoring_has_prometheus(self):
        """The monitoring supervisord config must define a prometheus program."""
        path = os.path.join(REPO_ROOT, "supervisord-monitoring.conf")
        with open(path) as fh:
            content = fh.read()
        assert "[program:prometheus]" in content

    def test_supervisord_monitoring_has_grafana(self):
        """The monitoring supervisord config must define a grafana program."""
        path = os.path.join(REPO_ROOT, "supervisord-monitoring.conf")
        with open(path) as fh:
            content = fh.read()
        assert "[program:grafana]" in content

    def test_prometheus_config_targets_localhost(self):
        """Prometheus should scrape metrics from localhost (in-container)."""
        prom_conf = os.path.join(REPO_ROOT, "monitoring", "prometheus", "prometheus.yml")
        with open(prom_conf) as fh:
            data = yaml.safe_load(fh)
        targets = data["scrape_configs"][0]["static_configs"][0]["targets"]
        assert any("127.0.0.1" in t for t in targets)

    def test_grafana_datasource_targets_localhost(self):
        """Grafana datasource should point to localhost Prometheus."""
        ds_conf = os.path.join(REPO_ROOT, "monitoring", "grafana", "provisioning", "datasources", "prometheus.yml")
        with open(ds_conf) as fh:
            data = yaml.safe_load(fh)
        url = data["datasources"][0]["url"]
        assert "127.0.0.1" in url

    def test_no_monitoring_overlay_exists(self):
        """docker-compose.monitoring.yml should not exist (monitoring is in-container)."""
        path = os.path.join(REPO_ROOT, "docker-compose.monitoring.yml")
        assert not os.path.isfile(path), "Monitoring overlay should not exist; Grafana/Prometheus run in-container"
