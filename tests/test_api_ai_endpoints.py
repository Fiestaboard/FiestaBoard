"""API tests for the AI page-generation endpoints.

Covers:
- /settings/ai GET/PUT round-trip with masked-key preservation,
- /pages/ai/generate happy path with a mocked generator,
- behavior when AI is disabled or no providers are configured,
- the rate-limit / throttle.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.api_server import app
from src.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def reset_config_singleton(tmp_path, monkeypatch):
    """Force a fresh ConfigManager backed by a tmp file for every test."""
    ConfigManager._instance = None  # type: ignore[attr-defined]
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_path))
    monkeypatch.setattr("src.api_server.get_config_manager", lambda: cm)
    # Reset the rate-limit so back-to-back tests aren't throttled by the
    # 1-second min interval. We use monkeypatch to keep things isolated.
    monkeypatch.setattr("src.api_server._ai_generate_last_call", 0.0)
    yield cm
    ConfigManager._instance = None  # type: ignore[attr-defined]


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# /settings/ai
# ---------------------------------------------------------------------------


def test_get_ai_settings_returns_defaults_when_unset(client):
    res = client.get("/settings/ai")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is False
    assert body["providers"] == []
    assert body["default_provider_id"] is None


def test_put_ai_settings_round_trips_provider(client):
    payload = {
        "enabled": True,
        "providers": [
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-real-secret",
                "models": ["openai/gpt-4o-mini"],
                "default_model": "openai/gpt-4o-mini",
                "headers": {},
            }
        ],
        "default_provider_id": "openrouter",
    }
    res = client.put("/settings/ai", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert body["default_provider_id"] == "openrouter"
    # api_key must be masked in the response.
    assert body["providers"][0]["api_key"] == "***"
    # But unmasked when read internally.
    cm = res.request  # noqa: F841 — placeholder, cm fetched fresh below.

    # Round-trip: GET should also mask.
    res2 = client.get("/settings/ai")
    assert res2.json()["providers"][0]["api_key"] == "***"


def test_put_ai_settings_preserves_key_when_mask_is_resent(client, reset_config_singleton):
    cm = reset_config_singleton

    # Initial set with real key.
    client.put(
        "/settings/ai",
        json={
            "enabled": True,
            "providers": [
                {
                    "id": "openrouter",
                    "name": "OpenRouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "sk-real-secret",
                    "models": ["m1"],
                    "default_model": "m1",
                }
            ],
            "default_provider_id": "openrouter",
        },
    )
    assert cm.get_ai_provider("openrouter")["api_key"] == "sk-real-secret"

    # Resubmit with the mask placeholder. Real key must be preserved.
    res = client.put(
        "/settings/ai",
        json={
            "providers": [
                {
                    "id": "openrouter",
                    "name": "OpenRouter (renamed)",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "***",
                    "models": ["m1", "m2"],
                    "default_model": "m2",
                }
            ],
        },
    )
    assert res.status_code == 200
    stored = cm.get_ai_provider("openrouter")
    assert stored["api_key"] == "sk-real-secret"
    assert stored["name"] == "OpenRouter (renamed)"
    assert stored["models"] == ["m1", "m2"]


def test_put_ai_settings_rejects_non_object_body(client):
    res = client.put("/settings/ai", json=["not", "an", "object"])
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# /pages/ai/generate
# ---------------------------------------------------------------------------


def _seed_provider(cm, *, enabled: bool = True):
    cm.set_ai_providers(
        {
            "enabled": enabled,
            "providers": [
                {
                    "id": "p1",
                    "name": "Test",
                    "base_url": "https://example.test/v1",
                    "api_key": "secret",
                    "models": ["test-model"],
                    "default_model": "test-model",
                }
            ],
            "default_provider_id": "p1",
        }
    )


def test_generate_page_disabled_returns_400(client, reset_config_singleton):
    _seed_provider(reset_config_singleton, enabled=False)
    res = client.post(
        "/pages/ai/generate",
        json={"prompt": "hi", "device_type": "flagship"},
    )
    assert res.status_code == 400
    assert "not enabled" in res.json()["detail"].lower()


def test_generate_page_no_providers_returns_400(client, reset_config_singleton):
    cm = reset_config_singleton
    cm.set_ai_providers({"enabled": True, "providers": []})
    res = client.post(
        "/pages/ai/generate",
        json={"prompt": "hi", "device_type": "flagship"},
    )
    assert res.status_code == 400


def test_generate_page_missing_prompt_returns_400(client, reset_config_singleton):
    _seed_provider(reset_config_singleton)
    res = client.post(
        "/pages/ai/generate",
        json={"device_type": "flagship"},
    )
    assert res.status_code == 400


def test_generate_page_invalid_device_returns_400(client, reset_config_singleton):
    _seed_provider(reset_config_singleton)
    res = client.post(
        "/pages/ai/generate",
        json={"prompt": "x", "device_type": "billboard"},
    )
    assert res.status_code == 400


def test_generate_page_happy_path_mocks_generator(client, reset_config_singleton):
    _seed_provider(reset_config_singleton)

    fake_result = {
        "page": {
            "name": "AI Time",
            "type": "template",
            "device_type": "flagship",
            "template": ["", "12:34", "", "", "", ""],
            "line_metadata": [
                {"alignment": "center", "wrap": False} for _ in range(6)
            ],
            "duration_seconds": 60,
        },
        "model_used": "test-model",
        "provider_id": "p1",
        "warnings": [],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    async def fake_generate(**kwargs):
        # Verify wiring: provider config & device_type are forwarded.
        assert kwargs["device_type"] == "flagship"
        assert kwargs["providers_block"]["providers"][0]["api_key"] == "secret"
        return fake_result

    with patch("src.ai.generator.generate_page", side_effect=fake_generate):
        res = client.post(
            "/pages/ai/generate",
            json={"prompt": "Show me the time", "device_type": "flagship"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["page"]["name"] == "AI Time"
    assert body["model_used"] == "test-model"
    assert body["warnings"] == []


def test_generate_page_surfaces_ai_errors_as_400(client, reset_config_singleton):
    _seed_provider(reset_config_singleton)

    from src.ai.generator import AIGenerationError

    async def fake_generate(**kwargs):
        raise AIGenerationError("Bad model output: foo")

    with patch("src.ai.generator.generate_page", side_effect=fake_generate):
        res = client.post(
            "/pages/ai/generate",
            json={"prompt": "x", "device_type": "flagship"},
        )
    assert res.status_code == 400
    assert "Bad model output" in res.json()["detail"]


def test_generate_page_throttles_back_to_back_calls(client, reset_config_singleton, monkeypatch):
    _seed_provider(reset_config_singleton)

    fake_result = {
        "page": {
            "name": "ok",
            "type": "template",
            "device_type": "flagship",
            "template": [""] * 6,
            "line_metadata": [
                {"alignment": "left", "wrap": False} for _ in range(6)
            ],
            "duration_seconds": 60,
        },
        "model_used": "test-model",
        "provider_id": "p1",
        "warnings": [],
        "usage": {},
    }

    async def fake_generate(**kwargs):
        return fake_result

    with patch("src.ai.generator.generate_page", side_effect=fake_generate):
        res1 = client.post(
            "/pages/ai/generate",
            json={"prompt": "x", "device_type": "flagship"},
        )
        assert res1.status_code == 200
        # Second call within the throttle interval is rejected.
        res2 = client.post(
            "/pages/ai/generate",
            json={"prompt": "x", "device_type": "flagship"},
        )
        assert res2.status_code == 429


# ---------------------------------------------------------------------------
# /pages/ai/context (debug endpoint)
# ---------------------------------------------------------------------------


def test_get_ai_context_includes_dimensions(client):
    res = client.get("/pages/ai/context?device_type=note")
    assert res.status_code == 200
    body = res.json()
    assert body["device_type"] == "note"
    assert body["rows"] == 3
    assert body["cols"] == 15
    assert "system_prompt" in body
    # No API keys should ever appear in the context.
    assert "Bearer" not in body["system_prompt"]


def test_get_ai_context_rejects_invalid_device(client):
    res = client.get("/pages/ai/context?device_type=potato")
    assert res.status_code == 400
