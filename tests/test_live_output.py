"""Tests for the live output feature (POST /templates/render/live)."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


class TestRenderTemplateLiveEndpoint:
    """Tests for POST /templates/render/live API endpoint."""

    @pytest.fixture
    def client(self):
        from src.api_server import app
        return TestClient(app)

    def test_missing_template_returns_400(self, client):
        """Template parameter is required."""
        response = client.post("/templates/render/live", json={})
        assert response.status_code == 400
        assert "template parameter required" in response.json()["detail"]

    def test_empty_list_returns_empty_without_sending(self, client):
        """Empty template list returns empty lines and does not send to board."""
        response = client.post("/templates/render/live", json={"template": []})
        assert response.status_code == 200
        data = response.json()
        assert data["line_count"] == 6
        assert all(line == "" for line in data["lines"])
        assert data["sent_to_board"] is False

    def test_all_blank_lines_returns_empty_without_sending(self, client):
        """All-blank template returns empty without sending."""
        response = client.post("/templates/render/live", json={
            "template": ["", "", "", "", "", ""]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False
        assert data["line_count"] == 6

    def test_whitespace_only_template_returns_empty(self, client):
        """Whitespace-only strings are treated as empty."""
        response = client.post("/templates/render/live", json={
            "template": ["   ", "  "]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False

    def test_empty_string_template_returns_empty(self, client):
        """Empty string template returns empty without sending."""
        response = client.post("/templates/render/live", json={"template": ""})
        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False
        assert data["line_count"] == 6

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_render_with_content_and_no_boards(self, mock_settings, mock_engine, client):
        """Template with content renders but does not send when no boards configured."""
        engine = Mock()
        engine.render_lines.return_value = "Hello World\n\n\n\n\n"
        mock_engine.return_value = engine

        board_settings = Mock()
        board_settings.boards = []
        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        mock_settings.return_value = settings

        response = client.post("/templates/render/live", json={
            "template": ["Hello World"]
        })
        assert response.status_code == 200
        data = response.json()
        assert "Hello World" in data["rendered"]
        assert data["sent_to_board"] is False
        assert data["board_id"] is None

    @patch('src.api_server.board_client_from_board_dict')
    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_render_and_send_to_default_board(self, mock_settings, mock_engine, mock_client_factory, client):
        """Content is rendered and sent to the first board when no board_id specified."""
        engine = Mock()
        engine.render_lines.return_value = "Hello Board\n\n\n\n\n"
        mock_engine.return_value = engine

        mock_board_client = Mock()
        mock_board_client.send_characters.return_value = (True, True)
        mock_client_factory.return_value = mock_board_client

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Living Room", "device_type": "flagship"}
        ]
        transition_settings = Mock()
        transition_settings.strategy = "column"
        transition_settings.step_interval_ms = 500
        transition_settings.step_size = 2

        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        settings.get_transition_settings.return_value = transition_settings
        mock_settings.return_value = settings

        response = client.post("/templates/render/live", json={
            "template": ["Hello Board"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is True
        assert data["board_id"] == "board-1"
        assert "Hello Board" in data["rendered"]

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_render_and_send_to_specific_board(self, mock_settings, mock_engine, client):
        """Content is sent to a specific board when board_id is provided."""
        engine = Mock()
        engine.render_lines.return_value = "Hello Note\n\n\n"
        mock_engine.return_value = engine

        mock_board_client = Mock()
        mock_board_client.send_characters.return_value = (True, True)

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Flagship", "device_type": "flagship"},
            {"id": "board-2", "name": "Note", "device_type": "note"},
        ]
        transition_settings = Mock()
        transition_settings.strategy = None
        transition_settings.step_interval_ms = None
        transition_settings.step_size = None

        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        settings.get_transition_settings.return_value = transition_settings
        mock_settings.return_value = settings

        with patch('src.api_server.board_client_from_board_dict', return_value=mock_board_client):
            response = client.post("/templates/render/live", json={
                "template": ["Hello Note"],
                "board_id": "board-2",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is True
        assert data["board_id"] == "board-2"

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_nonexistent_board_id_returns_404(self, mock_settings, mock_engine, client):
        """Requesting a non-existent board_id returns 404."""
        engine = Mock()
        engine.render_lines.return_value = "Hello\n\n\n\n\n"
        mock_engine.return_value = engine

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Flagship", "device_type": "flagship"},
        ]
        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        mock_settings.return_value = settings

        response = client.post("/templates/render/live", json={
            "template": ["Hello"],
            "board_id": "nonexistent-board",
        })
        assert response.status_code == 404
        assert "Board not found" in response.json()["detail"]

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_board_client_none_skips_send(self, mock_settings, mock_engine, client):
        """When board_client_from_board_dict returns None, send is skipped."""
        engine = Mock()
        engine.render_lines.return_value = "Hello\n\n\n\n\n"
        mock_engine.return_value = engine

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Unconfigured", "device_type": "flagship"}
        ]
        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        mock_settings.return_value = settings

        with patch('src.api_server.board_client_from_board_dict', return_value=None):
            response = client.post("/templates/render/live", json={
                "template": ["Hello"]
            })

        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_board_send_failure_returns_sent_false(self, mock_settings, mock_engine, client):
        """When the board client raises an exception, sent_to_board is False."""
        engine = Mock()
        engine.render_lines.return_value = "Hello\n\n\n\n\n"
        mock_engine.return_value = engine

        mock_board_client = Mock()
        mock_board_client.send_characters.side_effect = Exception("Connection refused")

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Flagship", "device_type": "flagship"}
        ]
        transition_settings = Mock()
        transition_settings.strategy = None
        transition_settings.step_interval_ms = None
        transition_settings.step_size = None

        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        settings.get_transition_settings.return_value = transition_settings
        mock_settings.return_value = settings

        with patch('src.api_server.board_client_from_board_dict', return_value=mock_board_client):
            response = client.post("/templates/render/live", json={
                "template": ["Hello"]
            })

        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_board_not_actually_sent_returns_false(self, mock_settings, mock_engine, client):
        """When send_characters returns (True, False), sent_to_board is False (skipped unchanged)."""
        engine = Mock()
        engine.render_lines.return_value = "Hello\n\n\n\n\n"
        mock_engine.return_value = engine

        mock_board_client = Mock()
        mock_board_client.send_characters.return_value = (True, False)

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Flagship", "device_type": "flagship"}
        ]
        transition_settings = Mock()
        transition_settings.strategy = None
        transition_settings.step_interval_ms = None
        transition_settings.step_size = None

        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        settings.get_transition_settings.return_value = transition_settings
        mock_settings.return_value = settings

        with patch('src.api_server.board_client_from_board_dict', return_value=mock_board_client):
            response = client.post("/templates/render/live", json={
                "template": ["Hello"]
            })

        assert response.status_code == 200
        data = response.json()
        assert data["sent_to_board"] is False

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_string_template_rendered(self, mock_settings, mock_engine, client):
        """String templates (not lists) are rendered correctly."""
        engine = Mock()
        engine.render.return_value = "72 degrees"
        mock_engine.return_value = engine

        board_settings = Mock()
        board_settings.boards = []
        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        mock_settings.return_value = settings

        response = client.post("/templates/render/live", json={
            "template": "{{weather.temperature}} degrees"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["rendered"] == "72 degrees"
        assert data["sent_to_board"] is False

    @patch('src.api_server.get_template_engine')
    def test_template_render_error_returns_400(self, mock_engine, client):
        """Template rendering errors return 400."""
        engine = Mock()
        engine.render_lines.side_effect = Exception("Render failed")
        mock_engine.return_value = engine

        response = client.post("/templates/render/live", json={
            "template": ["{{bad_template}}"]
        })
        assert response.status_code == 400
        assert "Template rendering failed" in response.json()["detail"]

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_force_flag_passed_to_board_client(self, mock_settings, mock_engine, client):
        """The force=True flag is passed to send_characters to bypass skip-unchanged."""
        engine = Mock()
        engine.render_lines.return_value = "Hello\n\n\n\n\n"
        mock_engine.return_value = engine

        mock_board_client = Mock()
        mock_board_client.send_characters.return_value = (True, True)

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Flagship", "device_type": "flagship"}
        ]
        transition_settings = Mock()
        transition_settings.strategy = "column"
        transition_settings.step_interval_ms = 100
        transition_settings.step_size = 1

        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        settings.get_transition_settings.return_value = transition_settings
        mock_settings.return_value = settings

        with patch('src.api_server.board_client_from_board_dict', return_value=mock_board_client):
            client.post("/templates/render/live", json={
                "template": ["Hello"]
            })

        call_kwargs = mock_board_client.send_characters.call_args
        assert call_kwargs[1].get("force") is True or (len(call_kwargs[0]) > 4 and call_kwargs[0][4] is True)

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_note_device_type_uses_correct_dimensions(self, mock_settings, mock_engine, client):
        """When targeting a Note board, the correct 3x15 dimensions are used."""
        engine = Mock()
        engine.render_lines.return_value = "Hello\n\n\n"
        mock_engine.return_value = engine

        mock_board_client = Mock()
        mock_board_client.send_characters.return_value = (True, True)

        board_settings = Mock()
        board_settings.boards = [
            {"id": "note-1", "name": "Note", "device_type": "note"}
        ]
        transition_settings = Mock()
        transition_settings.strategy = None
        transition_settings.step_interval_ms = None
        transition_settings.step_size = None

        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        settings.get_transition_settings.return_value = transition_settings
        mock_settings.return_value = settings

        with patch('src.api_server.board_client_from_board_dict', return_value=mock_board_client) as mock_factory, \
             patch('src.api_server.text_to_board_array') as mock_t2b:
            mock_t2b.return_value = [[0] * 15] * 3
            mock_board_client.send_characters.return_value = (True, True)

            response = client.post("/templates/render/live", json={
                "template": ["Hello"],
                "board_id": "note-1",
            })

        assert response.status_code == 200
        mock_t2b.assert_called_once()
        call_kwargs = mock_t2b.call_args
        assert call_kwargs[1]["rows"] == 3
        assert call_kwargs[1]["cols"] == 15

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_response_includes_all_fields(self, mock_settings, mock_engine, client):
        """Response includes all expected fields."""
        engine = Mock()
        engine.render_lines.return_value = "Line 1\nLine 2\nLine 3\n\n\n"
        mock_engine.return_value = engine

        board_settings = Mock()
        board_settings.boards = []
        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        mock_settings.return_value = settings

        response = client.post("/templates/render/live", json={
            "template": ["Line 1", "Line 2", "Line 3"]
        })

        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        assert "lines" in data
        assert "line_count" in data
        assert "sent_to_board" in data
        assert "board_id" in data
        assert isinstance(data["lines"], list)
        assert isinstance(data["line_count"], int)
        assert isinstance(data["sent_to_board"], bool)

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_board_id_passed_in_empty_response(self, mock_settings, mock_engine, client):
        """board_id from request is included in empty template responses."""
        response = client.post("/templates/render/live", json={
            "template": [],
            "board_id": "my-board",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["board_id"] == "my-board"
        assert data["sent_to_board"] is False

    @patch('src.api_server.get_template_engine')
    @patch('src.api_server.get_settings_service')
    def test_transition_settings_passed_to_board(self, mock_settings, mock_engine, client):
        """System transition settings are passed to send_characters."""
        engine = Mock()
        engine.render_lines.return_value = "Test\n\n\n\n\n"
        mock_engine.return_value = engine

        mock_board_client = Mock()
        mock_board_client.send_characters.return_value = (True, True)

        board_settings = Mock()
        board_settings.boards = [
            {"id": "board-1", "name": "Flagship", "device_type": "flagship"}
        ]
        transition_settings = Mock()
        transition_settings.strategy = "diagonal"
        transition_settings.step_interval_ms = 200
        transition_settings.step_size = 3

        settings = Mock()
        settings.get_board_settings.return_value = board_settings
        settings.get_transition_settings.return_value = transition_settings
        mock_settings.return_value = settings

        with patch('src.api_server.board_client_from_board_dict', return_value=mock_board_client):
            client.post("/templates/render/live", json={
                "template": ["Test"]
            })

        mock_board_client.send_characters.assert_called_once()
        call_kwargs = mock_board_client.send_characters.call_args[1]
        assert call_kwargs["strategy"] == "diagonal"
        assert call_kwargs["step_interval_ms"] == 200
        assert call_kwargs["step_size"] == 3
