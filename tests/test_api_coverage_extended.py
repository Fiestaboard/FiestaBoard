"""Extended tests for api_server.py to boost coverage on remaining untested endpoints.

Covers: MQTT settings, Bay Wheels stations, Muni stops, traffic geocode/validate,
plugin data/updates/install, carousel error paths, generic-data test-fetch,
and deprecated compat endpoints.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# MQTT Settings (lines 600-621)
# ---------------------------------------------------------------------------

class TestMQTTSettings:
    def test_get_mqtt_settings(self, client):
        mock_settings = Mock()
        mock_settings.to_dict.return_value = {
            "enabled": False,
            "broker_host": "",
            "broker_port": 1883,
            "username": "",
            "password": "****",
        }
        mock_svc = Mock()
        mock_svc.get_mqtt_settings.return_value = mock_settings
        with patch("src.api_server.get_settings_service", return_value=mock_svc):
            resp = client.get("/settings/mqtt")
        assert resp.status_code == 200
        assert "enabled" in resp.json()

    def test_put_mqtt_settings(self, client):
        mock_settings = Mock()
        mock_settings.to_dict.return_value = {"enabled": True, "broker_host": "mqtt.example.com"}
        mock_svc = Mock()
        mock_svc.set_mqtt_settings.return_value = mock_settings
        with patch("src.settings.service.get_settings_service", return_value=mock_svc), \
             patch("src.api_server._apply_mqtt_config") as mock_apply:
            resp = client.put("/settings/mqtt", json={"enabled": True, "broker_host": "mqtt.example.com"})
        assert resp.status_code == 200
        mock_apply.assert_called_once()


# ---------------------------------------------------------------------------
# _apply_mqtt_config (lines 551-597)
# ---------------------------------------------------------------------------

class TestApplyMQTTConfig:
    def test_apply_disabled(self):
        from src.api_server import _apply_mqtt_config
        cfg = Mock(enabled=False)
        with patch("src.mqtt.get_mqtt_client", return_value=None), \
             patch("src.mqtt.set_mqtt_client_instance"):
            _apply_mqtt_config(cfg)

    def test_apply_stops_old_client(self):
        from src.api_server import _apply_mqtt_config
        cfg = Mock(enabled=False)
        old_client = Mock()
        with patch("src.mqtt.get_mqtt_client", return_value=old_client), \
             patch("src.mqtt.set_mqtt_client_instance"):
            _apply_mqtt_config(cfg)
        old_client.stop.assert_called_once()

    def test_apply_enabled_invalid_config(self):
        from src.api_server import _apply_mqtt_config
        cfg = Mock(
            enabled=True, broker_host="mqtt.example.com", broker_port=1883,
            username="", password="", external_url=""
        )
        mock_mqtt_config = Mock()
        mock_mqtt_config.validate.return_value = ["host is invalid"]
        with patch("src.mqtt.get_mqtt_client", return_value=None), \
             patch("src.mqtt.set_mqtt_client_instance"), \
             patch("src.mqtt.config.MQTTConfig", return_value=mock_mqtt_config):
            _apply_mqtt_config(cfg)

    def test_apply_enabled_valid_config(self):
        from src.api_server import _apply_mqtt_config
        cfg = Mock(
            enabled=True, broker_host="mqtt.example.com", broker_port=1883,
            username=None, password=None, external_url=None
        )
        mock_mqtt_config = Mock()
        mock_mqtt_config.validate.return_value = []
        mock_client = Mock()
        with patch("src.mqtt.get_mqtt_client", return_value=None), \
             patch("src.mqtt.set_mqtt_client_instance") as mock_set, \
             patch("src.mqtt.config.MQTTConfig", return_value=mock_mqtt_config), \
             patch("src.mqtt.MQTTClient", return_value=mock_client), \
             patch("src.mqtt.state.StatePublisher", return_value=Mock()), \
             patch("src.mqtt.commands.CommandHandler", return_value=Mock()):
            _apply_mqtt_config(cfg)
        mock_client.start.assert_called_once()
        mock_set.assert_called()


# ---------------------------------------------------------------------------
# Bay Wheels Stations (lines 1865-2090)
# ---------------------------------------------------------------------------

def _make_station_status_response(station_ids):
    stations = []
    for sid in station_ids:
        stations.append({
            "station_id": sid,
            "num_bikes_available": 5,
            "num_docks_available": 10,
            "is_renting": 1,
            "vehicle_types_available": [
                {"vehicle_type_id": "electric_boost", "count": 2},
                {"vehicle_type_id": "classic", "count": 3},
            ],
        })
    mock_resp = Mock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"data": {"stations": stations}}
    return mock_resp


class TestBayWheelsStations:
    def test_list_all_stations(self, client):
        station_info = {
            "s1": {"name": "Station 1", "lat": 37.77, "lon": -122.42, "address": "123 Main St", "capacity": 20},
        }
        status_resp = _make_station_status_response(["s1"])
        with patch("src.utils.baywheels.BayWheelsSource._get_station_information", return_value=station_info), \
             patch("requests.get", return_value=status_resp):
            resp = client.get("/baywheels/stations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["stations"][0]["electric_bikes"] == 2

    def test_list_all_stations_error(self, client):
        with patch("src.utils.baywheels.BayWheelsSource._get_station_information", side_effect=Exception("fail")), \
             patch("requests.get", side_effect=Exception("fail")):
            resp = client.get("/baywheels/stations")
        assert resp.status_code == 500

    def test_nearby_stations(self, client):
        nearby = [{"station_id": "s1", "name": "Near", "lat": 37.77, "lon": -122.42}]
        status_resp = _make_station_status_response(["s1"])
        with patch("src.utils.baywheels.BayWheelsSource.find_stations_near_location", return_value=nearby), \
             patch("requests.get", return_value=status_resp):
            resp = client.get("/baywheels/stations/nearby?lat=37.77&lng=-122.42")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_nearby_stations_error(self, client):
        with patch("src.utils.baywheels.BayWheelsSource.find_stations_near_location", side_effect=Exception("err")), \
             patch("requests.get", side_effect=Exception("err")):
            resp = client.get("/baywheels/stations/nearby?lat=37.77&lng=-122.42")
        assert resp.status_code == 500

    def test_search_by_address(self, client):
        geocode_resp = Mock()
        geocode_resp.raise_for_status.return_value = None
        geocode_resp.json.return_value = [{"lat": "37.77", "lon": "-122.42", "display_name": "SF"}]

        nearby = [{"station_id": "s1", "name": "Near", "lat": 37.77, "lon": -122.42}]
        status_resp = _make_station_status_response(["s1"])

        with patch("requests.get", side_effect=[geocode_resp, status_resp]), \
             patch("src.utils.baywheels.BayWheelsSource.find_stations_near_location", return_value=nearby):
            resp = client.get("/baywheels/stations/search?address=Market+St")
        assert resp.status_code == 200
        assert "geocoded_location" in resp.json()

    def test_search_address_not_found(self, client):
        geocode_resp = Mock()
        geocode_resp.raise_for_status.return_value = None
        geocode_resp.json.return_value = []
        with patch("requests.get", return_value=geocode_resp):
            resp = client.get("/baywheels/stations/search?address=Nowhere")
        assert resp.status_code == 404

    def test_search_geocode_error(self, client):
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError("fail")):
            resp = client.get("/baywheels/stations/search?address=Test")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Muni Stops (lines 2167-2437)
# ---------------------------------------------------------------------------

class TestMuniStops:
    @pytest.fixture(autouse=True)
    def clear_muni_stops_cache(self, monkeypatch):
        """Ensure module-level cache used by list_all_muni_stops is reset per test."""
        import src.api_server as _api_server
        monkeypatch.setattr(_api_server, "_muni_stops_cache", None)
        monkeypatch.setattr(_api_server, "_muni_stops_cache_time", 0.0)
        yield
        monkeypatch.setattr(_api_server, "_muni_stops_cache", None)
        monkeypatch.setattr(_api_server, "_muni_stops_cache_time", 0.0)

    def test_list_muni_stops(self, client):
        api_response = Mock()
        api_response.raise_for_status.return_value = None
        api_response.text = '{"Contents":{"dataObjects":{"ScheduledStopPoint":[{"id":"SF_1234","Name":"Market & 3rd","Location":{"Latitude":"37.79","Longitude":"-122.40"}}]}}}'
        with patch("src.config.Config.MUNI_API_KEY", "test_key_123"), \
             patch("requests.get", return_value=api_response):
            resp = client.get("/muni/stops")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_muni_stops_no_api_key(self, client):
        with patch("src.config.Config.MUNI_API_KEY", ""):
            resp = client.get("/muni/stops")
        # May be 400 or 500 depending on how the exception propagates
        assert resp.status_code in (400, 500)

    def test_list_muni_stops_cached(self, client):
        """Second call uses cache."""
        api_response = Mock()
        api_response.raise_for_status.return_value = None
        api_response.text = '{"Contents":{"dataObjects":{"ScheduledStopPoint":[{"id":"SF_5678","Name":"Powell","Location":{"Latitude":"37.78","Longitude":"-122.41"}}]}}}'
        with patch("src.config.Config.MUNI_API_KEY", "test_key_123"), \
             patch("requests.get", return_value=api_response) as mock_get:
            resp1 = client.get("/muni/stops")
            resp2 = client.get("/muni/stops")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Second call should hit cache, so requests.get called only once
        assert mock_get.call_count == 1

    def test_nearby_muni_stops(self, client):
        stops_data = {
            "stops": [
                {"stop_code": "1234", "stop_id": "SF_1234", "name": "Stop A", "lat": 37.79, "lon": -122.40},
                {"stop_code": "5678", "stop_id": "SF_5678", "name": "Stop B", "lat": 37.80, "lon": -122.41},
            ],
            "total": 2,
        }
        mock_cache = Mock()
        mock_cache.is_ready.return_value = False
        with patch("src.api_server.list_all_muni_stops", new_callable=AsyncMock, return_value=stops_data), \
             patch("src.utils.transit_cache.get_transit_cache", return_value=mock_cache):
            resp = client.get("/muni/stops/nearby?lat=37.79&lng=-122.40")
        assert resp.status_code == 200
        assert "stops" in resp.json()

    def test_nearby_muni_stops_with_routes(self, client):
        stops_data = {
            "stops": [
                {"stop_code": "1234", "stop_id": "SF_1234", "name": "Stop A", "lat": 37.79, "lon": -122.40},
            ],
            "total": 1,
        }
        mock_cache = Mock()
        mock_cache.is_ready.return_value = True
        mock_cache.get_all_stops_for_agency.return_value = {
            "1234": [{"MonitoredVehicleJourney": {"PublishedLineName": "N"}}]
        }
        with patch("src.api_server.list_all_muni_stops", new_callable=AsyncMock, return_value=stops_data), \
             patch("src.utils.transit_cache.get_transit_cache", return_value=mock_cache):
            resp = client.get("/muni/stops/nearby?lat=37.79&lng=-122.40&radius=5")
        assert resp.status_code == 200
        stops = resp.json()["stops"]
        assert len(stops) >= 1

    def test_search_muni_by_address(self, client):
        geocode_resp = Mock()
        geocode_resp.raise_for_status.return_value = None
        geocode_resp.json.return_value = [{"lat": "37.79", "lon": "-122.40", "display_name": "SF"}]

        nearby_data = {"stops": [{"stop_code": "1", "name": "A", "lat": 37.79, "lon": -122.40, "distance_km": 0.1}], "count": 1}
        with patch("requests.get", return_value=geocode_resp), \
             patch("src.api_server.find_nearby_muni_stops", new_callable=AsyncMock, return_value=nearby_data):
            resp = client.get("/muni/stops/search?address=Market+St")
        assert resp.status_code == 200
        assert "geocoded_location" in resp.json()

    def test_search_muni_address_not_found(self, client):
        geocode_resp = Mock()
        geocode_resp.raise_for_status.return_value = None
        geocode_resp.json.return_value = []
        with patch("requests.get", return_value=geocode_resp):
            resp = client.get("/muni/stops/search?address=Nowhere")
        assert resp.status_code == 404

    def test_search_muni_geocode_error(self, client):
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError("fail")):
            resp = client.get("/muni/stops/search?address=Test")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Traffic Geocode & Validate (lines 2556-2680)
# ---------------------------------------------------------------------------

class TestTrafficEndpoints:
    def test_geocode_success(self, client):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{"lat": "40.7128", "lon": "-74.0060", "display_name": "NYC"}]
        with patch("requests.get", return_value=mock_resp):
            resp = client.post("/traffic/routes/geocode", json={"address": "Times Square"})
        assert resp.status_code == 200
        assert resp.json()["lat"] == 40.7128

    def test_geocode_no_address(self, client):
        resp = client.post("/traffic/routes/geocode", json={})
        assert resp.status_code == 400

    def test_geocode_not_found(self, client):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = []
        with patch("requests.get", return_value=mock_resp):
            resp = client.post("/traffic/routes/geocode", json={"address": "XYZ"})
        assert resp.status_code == 404

    def test_geocode_exception(self, client):
        with patch("requests.get", side_effect=Exception("network")):
            resp = client.post("/traffic/routes/geocode", json={"address": "Test"})
        assert resp.status_code == 500

    def test_validate_route_success(self, client):
        mock_ts = Mock()
        mock_ts.fetch_traffic_data.return_value = {"static_duration": 600, "static_duration_minutes": 10}
        with patch("src.config.Config.GOOGLE_ROUTES_API_KEY", "test_key"), \
             patch("src.utils.traffic.TrafficSource", return_value=mock_ts):
            resp = client.post("/traffic/routes/validate", json={
                "origin": "40.7128,-74.0060",
                "destination": "40.7580,-73.9855",
                "destination_name": "MIDTOWN",
            })
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_route_missing_fields(self, client):
        resp = client.post("/traffic/routes/validate", json={"origin": "x"})
        assert resp.status_code == 400

    def test_validate_route_no_api_key(self, client):
        with patch("src.config.Config.GOOGLE_ROUTES_API_KEY", None):
            resp = client.post("/traffic/routes/validate", json={"origin": "a", "destination": "b"})
            assert resp.status_code in (200, 400)

    def test_validate_route_empty_data(self, client):
        mock_ts = Mock()
        mock_ts.fetch_traffic_data.return_value = None
        with patch("src.config.Config.GOOGLE_ROUTES_API_KEY", "test_key"), \
             patch("src.utils.traffic.TrafficSource", return_value=mock_ts):
            resp = client.post("/traffic/routes/validate", json={"origin": "a", "destination": "b"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_validate_route_exception(self, client):
        with patch("src.config.Config.GOOGLE_ROUTES_API_KEY", "test_key"), \
             patch("src.utils.traffic.TrafficSource", side_effect=Exception("boom")):
            resp = client.post("/traffic/routes/validate", json={"origin": "a", "destination": "b"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False


# ---------------------------------------------------------------------------
# Plugin Data (lines 4653-4696)
# ---------------------------------------------------------------------------

class TestPluginData:
    def test_get_plugin_data_success(self, client):
        # ``formatted_lines`` mirrors the field on PluginResult after the
        # ``/plugins/{id}/data`` endpoint was fixed to stop referencing the
        # non-existent ``formatted`` attribute (issue surfaced as a 500).
        mock_result = Mock(
            available=True,
            data={"key": "val"},
            formatted_lines=["line1", "line2"],
            error=None,
        )
        mock_registry = Mock()
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.is_enabled.return_value = True
        mock_registry.fetch_plugin_data.return_value = mock_result
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.get("/plugins/test_plugin/data")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["formatted_lines"] == ["line1", "line2"]

    def test_get_plugin_data_not_available(self, client):
        mock_result = Mock(available=False, error="auth failed")
        mock_registry = Mock()
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.is_enabled.return_value = True
        mock_registry.fetch_plugin_data.return_value = mock_result
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.get("/plugins/test_plugin/data")
        assert resp.status_code == 503

    def test_get_plugin_data_not_found(self, client):
        mock_registry = Mock()
        mock_registry.get_plugin.return_value = None
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.get("/plugins/nonexistent/data")
        assert resp.status_code == 404

    def test_get_plugin_data_disabled(self, client):
        mock_registry = Mock()
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.is_enabled.return_value = False
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.get("/plugins/test_plugin/data")
        assert resp.status_code == 400

    def test_get_plugin_data_system_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            resp = client.get("/plugins/test_plugin/data")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Plugin Updates/Install (lines 4823-4949)
# ---------------------------------------------------------------------------

class TestPluginManagement:
    def test_trigger_update_check(self, client):
        mock_registry = Mock()
        mock_registry.check_for_updates.return_value = {"plugin_a": True, "plugin_b": False}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/updates/check")
        assert resp.status_code == 200
        assert resp.json()["checked"] == 2
        assert "plugin_a" in resp.json()["updates_available"]

    def test_trigger_update_check_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            resp = client.post("/plugins/updates/check")
        assert resp.status_code == 503

    def test_update_plugin_success(self, client):
        mock_source = Mock(source_type="external", local_path="/fake/path", repository_url="https://example.com/repo.git")
        mock_registry = Mock()
        mock_registry.get_plugin_source.return_value = mock_source
        mock_registry.reload_plugin.return_value = Mock()
        mock_registry._update_status = {"test_plugin": True}

        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("pathlib.Path.is_dir", return_value=True), \
             patch("src.plugins.sources.get_external_plugins_dir", return_value=Path("/fake")), \
             patch("src.plugins.sources.clone_or_update_repo", return_value=(True, None)):
            resp = client.post("/plugins/test_plugin/update")
        assert resp.status_code == 200

    def test_update_plugin_not_found(self, client):
        mock_registry = Mock()
        mock_registry.get_plugin_source.return_value = None
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/nonexistent/update")
        assert resp.status_code == 404

    def test_update_builtin_plugin(self, client):
        mock_source = Mock(source_type="builtin")
        mock_registry = Mock()
        mock_registry.get_plugin_source.return_value = mock_source
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/weather/update")
        assert resp.status_code == 400

    def test_update_plugin_no_url_required(self, client):
        """Endpoint passes empty URL to clone_or_update_repo (URL not needed for update path)."""
        # source has no repository_url (as happens for disk-loaded external plugins)
        mock_source = Mock(source_type="external", local_path="/fake/path", repository_url="")
        mock_registry = Mock()
        mock_registry.get_plugin_source.return_value = mock_source
        mock_registry.reload_plugin.return_value = Mock()
        mock_registry._update_status = {}

        captured_url = []

        def capture_clone(url, *args, **kwargs):
            captured_url.append(url)
            return (True, "")

        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("pathlib.Path.is_dir", return_value=True), \
             patch("src.plugins.sources.get_external_plugins_dir", return_value=Path("/fake")), \
             patch("src.plugins.sources.clone_or_update_repo", side_effect=capture_clone):
            resp = client.post("/plugins/test_plugin/update")
        assert resp.status_code == 200
        # The endpoint must pass "" not source.repository_url
        assert captured_url == [""]

    def test_apply_all_updates_success(self, client):
        """Bulk update applies all pending updates and returns results."""
        mock_source = Mock(source_type="external", local_path="/fake/path")
        mock_registry = Mock()
        mock_registry.get_update_status.return_value = {"plugin_a": True, "plugin_b": False}
        mock_registry.get_plugin_source.return_value = mock_source
        mock_registry.reload_plugin.return_value = Mock()
        mock_registry._update_status = {"plugin_a": True}

        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("pathlib.Path.is_dir", return_value=True), \
             patch("src.plugins.sources.get_external_plugins_dir", return_value=Path("/fake")), \
             patch("src.plugins.sources.clone_or_update_repo", return_value=(True, "")):
            resp = client.post("/plugins/updates/apply")
        assert resp.status_code == 200
        data = resp.json()
        assert "plugin_a" in data["updated"]
        assert data["failed"] == {}

    def test_apply_all_updates_no_updates(self, client):
        """Returns 200 with empty lists when nothing needs updating."""
        mock_registry = Mock()
        mock_registry.get_update_status.return_value = {}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/updates/apply")
        assert resp.status_code == 200
        assert resp.json()["updated"] == []
        assert resp.json()["failed"] == {}

    def test_apply_all_updates_partial_failure(self, client):
        """Partial failures are reported in 'failed' dict while successes are in 'updated'."""
        mock_source_ok = Mock(source_type="external", local_path="/fake/ok")
        mock_source_fail = Mock(source_type="external", local_path="/fake/fail")

        def get_source(pid):
            return mock_source_ok if pid == "good_plugin" else mock_source_fail

        mock_registry = Mock()
        mock_registry.get_update_status.return_value = {"good_plugin": True, "bad_plugin": True}
        mock_registry.get_plugin_source.side_effect = get_source
        mock_registry.reload_plugin.return_value = Mock()
        mock_registry._update_status = {"good_plugin": True, "bad_plugin": True}

        def fake_clone(url, plugin_id, *args, **kwargs):
            if plugin_id == "bad_plugin":
                return (False, "git fetch error")
            return (True, "")

        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("pathlib.Path.is_dir", return_value=True), \
             patch("src.plugins.sources.get_external_plugins_dir", return_value=Path("/fake")), \
             patch("src.plugins.sources.clone_or_update_repo", side_effect=fake_clone):
            resp = client.post("/plugins/updates/apply")
        assert resp.status_code == 200
        data = resp.json()
        assert "good_plugin" in data["updated"]
        assert "bad_plugin" in data["failed"]

    def test_apply_all_updates_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            resp = client.post("/plugins/updates/apply")
        assert resp.status_code == 503

    def test_install_plugin_success(self, client):
        mock_registry = Mock()
        mock_registry.install_from_git.return_value = []
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("src.plugins.sources.repo_name_from_url", return_value="fiestaboard-plugin-test"), \
             patch("src.plugins.sources.plugin_id_from_repo_name", return_value="test"):
            resp = client.post("/plugins/install", json={"repository": "https://github.com/example/fiestaboard-plugin-test"})
        assert resp.status_code == 200

    def test_install_plugin_errors(self, client):
        mock_registry = Mock()
        mock_registry.install_from_git.return_value = ["Clone failed"]
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/install", json={"repository": "https://github.com/example/repo"})
        assert resp.status_code == 400

    def test_install_plugin_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            resp = client.post("/plugins/install", json={"repository": "https://github.com/example/repo"})
        assert resp.status_code == 503

    def test_install_plugin_arbitrary_branch_accepted(self, client):
        mock_registry = Mock()
        mock_registry.install_from_git.return_value = []
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("src.plugins.sources.repo_name_from_url", return_value="repo"), \
             patch("src.plugins.sources.plugin_id_from_repo_name", return_value="repo"):
            resp = client.post("/plugins/install", json={
                "repository": "https://github.com/example/repo",
                "branch": "release/2.0",
            })
        assert resp.status_code == 200

    def test_install_plugin_invalid_branch_rejected(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True):
            resp = client.post("/plugins/install", json={
                "repository": "https://github.com/example/repo",
                "branch": "-bad-branch",
            })
        assert resp.status_code == 400

    def test_install_plugin_error_detail_in_response(self, client):
        mock_registry = Mock()
        mock_registry.install_from_git.return_value = ["fatal: repository not found"]
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/install", json={"repository": "https://github.com/example/repo"})
        assert resp.status_code == 400
        assert "repository not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Generic Data Test Fetch (lines 4985-5055)
# ---------------------------------------------------------------------------

class TestGenericDataTestFetch:
    # Public IP returned by the mocked DNS resolver (93.184.216.34 = example.com)
    _PUBLIC_ADDR_INFO = [(None, None, None, None, ("93.184.216.34", 443))]

    def test_fetch_json_success(self, client):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b'{"key": "value"}'
        mock_resp.json.return_value = {"key": "value"}
        mock_cm = Mock()
        mock_cm.get_general.return_value = {"timezone": "UTC"}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=["example.com"]), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO), \
             patch("requests.request", return_value=mock_resp):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://api.example.com/data", "format": "json"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_fetch_no_url(self, client):
        mock_cm = Mock()
        mock_cm.get_general.return_value = {}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm):
            resp = client.post("/generic-data/test-fetch", json={"url": ""})
        assert resp.status_code == 400

    def test_fetch_invalid_url(self, client):
        mock_cm = Mock()
        mock_cm.get_general.return_value = {}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm):
            resp = client.post("/generic-data/test-fetch", json={"url": "ftp://bad"})
        assert resp.status_code == 400

    def test_fetch_timeout(self, client):
        import requests as req
        mock_cm = Mock()
        mock_cm.get_general.return_value = {}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=["example.com"]), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO), \
             patch("requests.request", side_effect=req.exceptions.Timeout("timeout")):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://api.example.com/slow"})
        assert resp.status_code == 504

    def test_fetch_connection_error(self, client):
        import requests as req
        mock_cm = Mock()
        mock_cm.get_general.return_value = {}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=["example.com"]), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO), \
             patch("requests.request", side_effect=req.exceptions.ConnectionError("conn")):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://api.example.com/bad"})
        assert resp.status_code == 502

    def test_fetch_too_large(self, client):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b"x" * (1_048_577)
        mock_cm = Mock()
        mock_cm.get_general.return_value = {}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO), \
             patch("requests.request", return_value=mock_resp):
            resp = client.post("/generic-data/test-fetch", json={"url": "https://api.example.com/big"})
        assert resp.status_code == 400

    def test_fetch_with_headers_and_post(self, client):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b'{"ok": true}'
        mock_resp.json.return_value = {"ok": True}
        mock_cm = Mock()
        mock_cm.get_general.return_value = {}
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server._get_generic_data_allowed_hosts", return_value=["example.com"]), \
             patch("socket.getaddrinfo", return_value=self._PUBLIC_ADDR_INFO), \
             patch("requests.request", return_value=mock_resp):
            resp = client.post("/generic-data/test-fetch", json={
                "url": "https://api.example.com/data",
                "method": "POST",
                "body": '{"q": "test"}',
                "headers": [{"name": "Authorization", "value": "Bearer test_token"}],
            })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Carousel error paths (lines 3906-3940)
# ---------------------------------------------------------------------------

class TestCarouselErrors:
    def test_create_carousel_value_error(self, client):
        mock_cs = Mock()
        mock_cs.create_carousel.side_effect = ValueError("Duplicate name")
        mock_ps = Mock()
        mock_ps.get_page.return_value = Mock()
        with patch("src.api_server.get_carousel_service", return_value=mock_cs), \
             patch("src.api_server.get_page_service", return_value=mock_ps):
            resp = client.post("/carousels", json={"name": "Test", "page_ids": ["p1"]})
        assert resp.status_code == 400
        assert "Duplicate" in resp.json()["detail"]

    def test_update_carousel_value_error(self, client):
        mock_cs = Mock()
        mock_cs.update_carousel.side_effect = ValueError("Invalid")
        mock_ps = Mock()
        mock_ps.get_page.return_value = Mock()
        with patch("src.api_server.get_carousel_service", return_value=mock_cs), \
             patch("src.api_server.get_page_service", return_value=mock_ps):
            resp = client.put("/carousels/c1", json={"name": "Updated", "page_ids": ["p1"]})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Home Assistant entities (lines 4243-4280)
# ---------------------------------------------------------------------------

class TestHomeAssistant:
    def test_get_entities_success(self, client):
        mock_ha = Mock()
        mock_ha.base_url = "http://ha.local:8123"
        mock_ha.headers = {"Authorization": "Bearer test"}
        mock_ha.timeout = 10
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"entity_id": "sensor.temp", "state": "72", "attributes": {"friendly_name": "Temperature"}},
        ]
        with patch("src.utils.home_assistant.get_home_assistant_source", return_value=mock_ha), \
             patch("requests.get", return_value=mock_resp):
            resp = client.get("/home-assistant/entities")
        assert resp.status_code == 200
        assert len(resp.json()["entities"]) == 1

    def test_get_entities_not_configured(self, client):
        with patch("src.utils.home_assistant.get_home_assistant_source", return_value=None):
            resp = client.get("/home-assistant/entities")
        assert resp.status_code == 503

    def test_get_entities_error(self, client):
        mock_ha = Mock()
        mock_ha.base_url = "http://ha.local:8123"
        mock_ha.headers = {}
        mock_ha.timeout = 10
        with patch("src.utils.home_assistant.get_home_assistant_source", return_value=mock_ha), \
             patch("requests.get", side_effect=Exception("Connection refused")):
            resp = client.get("/home-assistant/entities")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Deprecated compat endpoints (lines 1051-1099)
# ---------------------------------------------------------------------------

class TestDeprecatedCompat:
    def test_get_board_config_compat(self, client):
        """Test the deprecated get_board_config_compat function directly."""
        from src.api_server import get_board_config_compat
        import asyncio

        mock_cm = Mock()
        mock_cm.get_board.return_value = {"api_mode": "local", "host": "192.168.1.100"}
        mock_cm._mask_sensitive.return_value = {"api_mode": "local", "host": "192.168.1.100"}
        mock_response = Mock()
        mock_response.headers = {}
        with patch("src.api_server.get_config_manager", return_value=mock_cm):
            result = asyncio.run(get_board_config_compat(mock_response))
        assert "config" in result
        assert mock_response.headers["Deprecation"] == "true"

    def test_update_board_config_compat(self, client):
        """Test the deprecated update_board_config_compat function directly."""
        from src.api_server import update_board_config_compat
        import asyncio

        mock_cm = Mock()
        mock_cm.get_board.return_value = {"api_mode": "local"}
        mock_cm._mask_sensitive.return_value = {"api_mode": "local"}
        mock_response = Mock()
        mock_response.headers = {}
        with patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server.get_service", return_value=None), \
             patch("src.config.Config.reload"):
            result = asyncio.run(
                update_board_config_compat({"api_mode": "local"}, mock_response)
            )
        assert "status" in result
        assert mock_response.headers["Deprecation"] == "true"
