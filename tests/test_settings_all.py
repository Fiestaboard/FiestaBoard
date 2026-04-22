"""Tests for consolidated settings endpoint."""
import pytest
from fastapi.testclient import TestClient
from src.api_server import app

client = TestClient(app)


def test_settings_all_success():
    """Test successful retrieval of all settings."""
    response = client.get("/settings/all")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check all required keys are present
    assert "general" in data
    assert "silence_schedule" in data
    assert "polling" in data
    assert "transitions" in data
    assert "output" in data
    assert "board" in data
    assert "status" in data


def test_settings_all_general_structure():
    """Test general settings structure."""
    response = client.get("/settings/all")
    data = response.json()
    
    general = data["general"]
    assert isinstance(general, dict)
    assert "timezone" in general
    assert isinstance(general["timezone"], str)


def test_settings_all_polling_structure():
    """Test polling settings structure."""
    response = client.get("/settings/all")
    data = response.json()
    
    polling = data["polling"]
    assert isinstance(polling, dict)
    assert "interval_seconds" in polling
    assert isinstance(polling["interval_seconds"], int)
    assert polling["interval_seconds"] > 0


def test_settings_all_transitions_structure():
    """Test transitions settings structure."""
    response = client.get("/settings/all")
    data = response.json()
    
    transitions = data["transitions"]
    assert isinstance(transitions, dict)
    # Transitions may have strategy, step_interval_ms, step_size
    # All are optional but should be present in dict


def test_settings_all_output_structure():
    """Test output settings structure."""
    response = client.get("/settings/all")
    data = response.json()
    
    output = data["output"]
    assert isinstance(output, dict)
    assert "target" in output
    assert output["target"] in ["ui", "board", "both"]


def test_settings_all_board_structure():
    """Test board settings structure."""
    response = client.get("/settings/all")
    data = response.json()
    
    board = data["board"]
    assert isinstance(board, dict)
    assert "board_type" in board
    # board_type can be "black", "white", or null


def test_settings_all_status_structure():
    """Test status structure."""
    response = client.get("/settings/all")
    data = response.json()
    
    status = data["status"]
    assert isinstance(status, dict)
    assert "running" in status
    assert isinstance(status["running"], bool)


def test_settings_all_silence_schedule_structure():
    """Test silence schedule structure.

    The UI expects the feature config wrapped as `{ "config": {...} }` so that
    `allSettings.silence_schedule.config.{enabled,start_time,end_time}` is
    accessible. See web/src/components/general-settings.tsx.
    """
    response = client.get("/settings/all")
    data = response.json()

    silence = data["silence_schedule"]
    assert isinstance(silence, dict)
    assert "config" in silence
    config = silence["config"]
    assert isinstance(config, dict)
    assert "enabled" in config
    assert "start_time" in config
    assert "end_time" in config
    assert isinstance(config["enabled"], bool)


def test_settings_all_consistency():
    """Test that settings/all returns consistent data with individual endpoints."""
    # Get all settings
    all_response = client.get("/settings/all")
    all_data = all_response.json()
    
    # Get individual polling settings
    polling_response = client.get("/settings/polling")
    polling_data = polling_response.json()
    
    # They should match
    assert all_data["polling"]["interval_seconds"] == polling_data["interval_seconds"]


def test_settings_all_board_consistency():
    """Test that board settings match between /all and /board endpoints."""
    # Get all settings
    all_response = client.get("/settings/all")
    all_data = all_response.json()
    
    # Get individual board settings
    board_response = client.get("/settings/board")
    board_data = board_response.json()
    
    # They should match
    assert all_data["board"]["board_type"] == board_data["board_type"]


def test_settings_all_response_time():
    """Test that consolidated endpoint is reasonably fast."""
    import time
    
    start = time.time()
    response = client.get("/settings/all")
    duration = time.time() - start
    
    assert response.status_code == 200
    # Should respond in less than 1 second
    assert duration < 1.0
