"""Unit tests for Sports Scores plugin."""

import pytest
from unittest.mock import patch, MagicMock, Mock
import json
from pathlib import Path

from plugins.sports_scores import SportsScoresPlugin
from src.plugins.base import PluginResult


class TestSportsScoresPlugin:
    """Test suite for SportsScoresPlugin."""
    
    def test_plugin_id(self, sample_manifest):
        """Test plugin ID matches directory name."""
        plugin = SportsScoresPlugin(sample_manifest)
        assert plugin.plugin_id == "sports_scores"
    
    def test_validate_config_valid(self, sample_manifest, sample_config):
        """Test config validation with valid config."""
        plugin = SportsScoresPlugin(sample_manifest)
        errors = plugin.validate_config(sample_config)
        assert len(errors) == 0
    
    def test_validate_config_no_sports(self, sample_manifest):
        """Test config validation detects missing sports."""
        plugin = SportsScoresPlugin(sample_manifest)
        errors = plugin.validate_config({"enabled": True})
        assert len(errors) > 0
        assert any("sport" in e.lower() for e in errors)
    
    def test_validate_config_invalid_sport(self, sample_manifest):
        """Test config validation detects invalid sport names."""
        plugin = SportsScoresPlugin(sample_manifest)
        errors = plugin.validate_config({
            "sports": ["InvalidSport", "NFL"]
        })
        assert len(errors) > 0
        assert any("invalid" in e.lower() for e in errors)
    
    def test_validate_refresh_too_low(self, sample_manifest):
        """Test base validation detects refresh interval too low."""
        plugin = SportsScoresPlugin(sample_manifest)
        errors = plugin._validate_refresh_seconds({
            "refresh_seconds": 30
        })
        assert len(errors) > 0
        assert any("at least 60 seconds" in e for e in errors)
    
    def test_validate_refresh_invalid_type(self, sample_manifest):
        """Test base validation detects invalid refresh_seconds type."""
        plugin = SportsScoresPlugin(sample_manifest)
        errors = plugin._validate_refresh_seconds({
            "refresh_seconds": "not_a_number"
        })
        assert len(errors) > 0
        assert any("must be a number" in e for e in errors)

    def test_validate_config_max_games_invalid(self, sample_manifest):
        """Test config validation detects invalid max_games_per_sport."""
        plugin = SportsScoresPlugin(sample_manifest)
        
        # Too low
        errors = plugin.validate_config({
            "sports": ["NFL"],
            "max_games_per_sport": 0
        })
        assert len(errors) > 0
        
        # Too high
        errors = plugin.validate_config({
            "sports": ["NFL"],
            "max_games_per_sport": 15
        })
        assert len(errors) > 0

    def test_validate_config_max_games_invalid_type(self, sample_manifest):
        """Test config validation detects invalid max_games_per_sport type."""
        plugin = SportsScoresPlugin(sample_manifest)
        errors = plugin.validate_config({
            "sports": ["NFL"],
            "max_games_per_sport": "not_a_number"
        })
        assert len(errors) > 0
        assert any("valid number" in e.lower() for e in errors)
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_success_free_tier(self, mock_get, sample_manifest, sample_config, mock_api_response_nfl):
        """Test successful data fetch with free tier API key."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_nfl
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.error is None
        assert result.data is not None
        assert "games" in result.data
        assert len(result.data["games"]) > 0
        assert result.data["sport_count"] == 2
        assert result.data["game_count"] > 0
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_success_with_api_key(self, mock_get, sample_manifest, sample_config, mock_api_response_nfl):
        """Test successful data fetch with custom API key."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_nfl
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {
            **sample_config,
            "api_key": "custom_key_123"
        }
        result = plugin.fetch_data()
        
        assert result.available is True
        # Verify API key was used in request
        call_args = mock_get.call_args
        assert "custom_key_123" in call_args[0][0] or "custom_key_123" in str(call_args)
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_no_sports(self, mock_get, sample_manifest):
        """Test fetch with no sports selected."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"enabled": True}
        result = plugin.fetch_data()
        
        assert result.available is False
        assert "sport" in result.error.lower()
        mock_get.assert_not_called()
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_rate_limit(self, mock_get, sample_manifest, sample_config):
        """Test handling of API rate limit (429)."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        # Should handle gracefully, may return empty games or error
        # The plugin should not crash
        assert result is not None
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_network_error(self, mock_get, sample_manifest, sample_config):
        """Test handling of network errors."""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Network error")
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        # Should handle gracefully
        assert result is not None
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_empty_response(self, mock_get, sample_manifest, sample_config, mock_api_response_empty):
        """Test handling of empty API response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_empty
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        # Should handle empty response
        assert result is not None
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_no_events(self, mock_get, sample_manifest, sample_config, mock_api_response_no_events):
        """Test handling when API returns no events."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_no_events
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is False
        assert "no games" in result.error.lower() or "no events" in result.error.lower()
    
    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_multiple_sports(self, mock_get, sample_manifest, sample_config, mock_api_response_nfl, mock_api_response_nba):
        """Test fetching data for multiple sports."""
        # Return different responses for different sports
        def side_effect(*args, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            mock_response.headers = {"content-type": "application/json"}
            
            # Check which sport is being requested
            if "American%20Football" in args[0] or "American" in str(kwargs):
                mock_response.json.return_value = mock_api_response_nfl
            elif "Basketball" in args[0] or "Basketball" in str(kwargs):
                mock_response.json.return_value = mock_api_response_nba
            else:
                mock_response.json.return_value = {"event": []}
            
            return mock_response
        
        mock_get.side_effect = side_effect
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data["sport_count"] == 2
        assert result.data["game_count"] > 0
        assert len(result.data["games"]) > 0
    
    @patch('plugins.sports_scores.requests.get')
    def test_parse_event_with_scores(self, mock_get, sample_manifest, sample_config, mock_api_response_nfl):
        """Test parsing event with scores."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_nfl
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        games = result.data["games"]
        assert len(games) > 0
        
        first_game = games[0]
        assert "team1" in first_game
        assert "team2" in first_game
        assert "score1" in first_game
        assert "score2" in first_game
        assert "formatted" in first_game
        assert first_game["score1"] >= 0
        assert first_game["score2"] >= 0
    
    @patch('plugins.sports_scores.requests.get')
    def test_parse_event_scheduled_game(self, mock_get, sample_manifest, sample_config):
        """Test parsing scheduled game (no scores yet)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "event": [
                {
                    "strEvent": "Lakers vs Warriors",
                    "strHomeTeam": "Los Angeles Lakers",
                    "strAwayTeam": "Golden State Warriors",
                    "intHomeScore": None,
                    "intAwayScore": None,
                    "strStatus": "Not Started",
                    "dateEvent": "2024-01-20",
                    "strTime": "22:30:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        games = result.data["games"]
        if len(games) > 0:
            game = games[0]
            assert game["score1"] == 0 or game["score1"] is not None
            assert game["score2"] == 0 or game["score2"] is not None
    
    @patch('plugins.sports_scores.requests.get')
    def test_max_games_per_sport_limit(self, mock_get, sample_manifest, sample_config):
        """Test that max_games_per_sport limit is respected."""
        # Create response with many events
        many_events = {
            "event": [
                {
                    "strEvent": f"Game {i}",
                    "strHomeTeam": f"Team A {i}",
                    "strAwayTeam": f"Team B {i}",
                    "intHomeScore": "10",
                    "intAwayScore": "5",
                    "strStatus": "Match Finished",
                    "dateEvent": "2024-01-15",
                    "strTime": "20:00:00"
                }
                for i in range(20)
            ]
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = many_events
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {
            **sample_config,
            "max_games_per_sport": 3
        }
        result = plugin.fetch_data()
        
        assert result.available is True
        # Should only get max_games_per_sport games per sport
        # With 2 sports and max 3 each, should have at most 6 games
        assert result.data["game_count"] <= 6
    
    def test_get_formatted_display(self, sample_manifest, sample_config):
        """Test get_formatted_display method."""
        with patch('plugins.sports_scores.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "event": [
                    {
                        "strEvent": "Lakers vs Warriors",
                        "strHomeTeam": "Los Angeles Lakers",
                        "strAwayTeam": "Golden State Warriors",
                        "intHomeScore": "98",
                        "intAwayScore": "95",
                        "strStatus": "Match Finished",
                        "dateEvent": "2024-01-15",
                        "strTime": "22:30:00"
                    }
                ]
            }
            mock_response.raise_for_status = Mock()
            mock_response.headers = {"content-type": "application/json"}
            mock_get.return_value = mock_response
            
            plugin = SportsScoresPlugin(sample_manifest)
            plugin.config = sample_config
            display = plugin.get_formatted_display()
            
            assert display is not None
            assert isinstance(display, list)
            assert len(display) == 6
            assert "SPORTS SCORES" in display[0]
    
    def test_get_formatted_display_no_cache(self, sample_manifest):
        """Test get_formatted_display when no cache exists."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"sports": []}  # Invalid config
        
        display = plugin.get_formatted_display()
        # Should return None when fetch fails
        assert display is None
    
    def test_data_variables_match_manifest(self, sample_manifest, sample_config):
        """Test that returned data includes variables declared in manifest."""
        import json
        from pathlib import Path
        
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        
        declared_simple = manifest["variables"]["simple"]
        
        with patch('plugins.sports_scores.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "event": [
                    {
                        "strEvent": "Test Game",
                        "strHomeTeam": "Team A",
                        "strAwayTeam": "Team B",
                        "intHomeScore": "10",
                        "intAwayScore": "5",
                        "strStatus": "Match Finished",
                        "dateEvent": "2024-01-15",
                        "strTime": "20:00:00"
                    }
                ]
            }
            mock_response.raise_for_status = Mock()
            mock_response.headers = {"content-type": "application/json"}
            mock_get.return_value = mock_response
            
            plugin = SportsScoresPlugin(sample_manifest)
            plugin.config = sample_config
            result = plugin.fetch_data()
            
            assert result.available is True
            for var in declared_simple:
                assert var in result.data, f"Variable '{var}' declared in manifest but not in data"


class TestPluginEdgeCases:
    """Tests for edge cases and error handling."""
    
    @patch('plugins.sports_scores.requests.get')
    def test_malformed_response_handling(self, mock_get, sample_manifest, sample_config):
        """Test handling of malformed API responses."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid": "data"}  # Missing "event" key
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        # Should handle gracefully
        assert result is not None
    
    @patch('plugins.sports_scores.requests.get')
    def test_timeout_handling(self, mock_get, sample_manifest, sample_config):
        """Test handling of request timeouts."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        # Should handle gracefully
        assert result is not None
    
    @patch('plugins.sports_scores.requests.get')
    def test_event_missing_teams(self, mock_get, sample_manifest, sample_config):
        """Test handling of events with missing team names."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "event": [
                {
                    "strEvent": "Invalid Game",
                    "strHomeTeam": "",  # Missing team
                    "strAwayTeam": "Team B",
                    "intHomeScore": "10",
                    "intAwayScore": "5",
                    "strStatus": "Match Finished",
                    "dateEvent": "2024-01-15",
                    "strTime": "20:00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        # Should skip invalid events
        assert result is not None
    
    @patch('plugins.sports_scores.requests.get')
    def test_color_variables_winning_team(self, mock_get, sample_manifest, sample_config):
        """Test that team1_color and team2_color return correct color codes for winning/losing teams."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "event": [
                {
                    "strEvent": "Team A vs Team B",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "intHomeScore": "24",
                    "intAwayScore": "17",
                    "strStatus": "Match Finished",
                    "dateEvent": "2024-01-15",
                    "strTime": "20:00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        games = result.data["games"]
        assert len(games) > 0
        
        game = games[0]
        # Team 1 (home) is winning (24 > 17), so team1_color should be GREEN {66}
        assert game["team1_color"] == "{66}"
        # Team 2 (away) is losing, so team2_color should be RED {63}
        assert game["team2_color"] == "{63}"
    
    @patch('plugins.sports_scores.requests.get')
    def test_color_variables_losing_team(self, mock_get, sample_manifest, sample_config):
        """Test that team1_color and team2_color return correct color codes when team1 is losing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "event": [
                {
                    "strEvent": "Team A vs Team B",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "intHomeScore": "10",
                    "intAwayScore": "20",
                    "strStatus": "Match Finished",
                    "dateEvent": "2024-01-15",
                    "strTime": "20:00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        games = result.data["games"]
        game = games[0]
        # Team 1 is losing (10 < 20), so team1_color should be RED {63}
        assert game["team1_color"] == "{63}"
        # Team 2 is winning, so team2_color should be GREEN {66}
        assert game["team2_color"] == "{66}"
    
    @patch('plugins.sports_scores.requests.get')
    def test_color_variables_tied_game(self, mock_get, sample_manifest, sample_config):
        """Test that team1_color and team2_color return YELLOW for tied games."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "event": [
                {
                    "strEvent": "Team A vs Team B",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "intHomeScore": "15",
                    "intAwayScore": "15",
                    "strStatus": "Match Finished",
                    "dateEvent": "2024-01-15",
                    "strTime": "20:00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        games = result.data["games"]
        game = games[0]
        # Both teams tied, so both should be YELLOW {65}
        assert game["team1_color"] == "{65}"
        assert game["team2_color"] == "{65}"
    
    @patch('plugins.sports_scores.requests.get')
    def test_color_variables_no_scores(self, mock_get, sample_manifest, sample_config):
        """Test that team1_color and team2_color return BLUE when no scores are available."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "event": [
                {
                    "strEvent": "Team A vs Team B",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "intHomeScore": None,
                    "intAwayScore": None,
                    "strStatus": "Not Started",
                    "dateEvent": "2024-01-20",
                    "strTime": "20:00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        games = result.data["games"]
        if len(games) > 0:
            game = games[0]
            # No scores (0-0), so both should be BLUE {67}
            assert game["team1_color"] == "{67}"
            assert game["team2_color"] == "{67}"
            # Formatted string should use "? - ?" for scores
            assert "? - ?" in game["formatted"]
    
    def test_abbreviate_team_name_removes_spaces(self, sample_manifest):
        """Test that team name abbreviation removes spaces."""
        plugin = SportsScoresPlugin(sample_manifest)
        
        # Test that spaces are removed
        result = plugin._abbreviate_team_name("Real Sociedad", 10)
        assert " " not in result
        assert "Soc" in result or "Real" in result
        
        # Test common abbreviation
        result = plugin._abbreviate_team_name("Real Sociedad", 5)
        assert " " not in result
        assert len(result) <= 5
    
    def test_format_game_string_exact_width(self, sample_manifest):
        """Test that formatted game string is exactly 20 characters (for use with color tiles)."""
        plugin = SportsScoresPlugin(sample_manifest)
        
        # Test with scores
        formatted = plugin._format_game_string("Team A", "Team B", 24, 17, max_length=20)
        assert len(formatted) == 20
        
        # Test with no scores (should use "? - ?")
        formatted = plugin._format_game_string("Team A", "Team B", 0, 0, max_length=20)
        assert len(formatted) == 20
        assert "? - ?" in formatted
    
    def test_format_game_string_alignment(self, sample_manifest):
        """Test that formatted game string aligns scores vertically."""
        plugin = SportsScoresPlugin(sample_manifest)
        
        # Format multiple games and check that scores align
        game1 = plugin._format_game_string("Short", "LongTeamName", 100, 99, max_length=20)
        game2 = plugin._format_game_string("VeryLongTeam", "Short", 50, 49, max_length=20)
        
        # Both should be exactly 20 characters
        assert len(game1) == 20
        assert len(game2) == 20
        
        # Find the position of the score separator "-" - it should be similar
        # (allowing for slight variation due to team name lengths)
        dash_pos_1 = game1.find(" - ")
        dash_pos_2 = game2.find(" - ")
        # The dash should be in roughly the same position (within 2 chars for alignment)
        assert abs(dash_pos_1 - dash_pos_2) <= 2
    
    def test_format_game_string_no_scores_question_marks(self, sample_manifest):
        """Test that formatted string uses "? - ?" when no scores are available."""
        plugin = SportsScoresPlugin(sample_manifest)
        
        formatted = plugin._format_game_string("Team A", "Team B", 0, 0, max_length=20)
        assert "? - ?" in formatted
        assert formatted.count("?") >= 2  # Should have at least 2 question marks
    
    @patch('plugins.sports_scores.requests.get')
    def test_formatted_string_includes_color_variables(self, mock_get, sample_manifest, sample_config):
        """Test that games include both formatted string and color variables."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "event": [
                {
                    "strEvent": "Team A vs Team B",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "intHomeScore": "24",
                    "intAwayScore": "17",
                    "strStatus": "Match Finished",
                    "dateEvent": "2024-01-15",
                    "strTime": "20:00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        
        assert result.available is True
        games = result.data["games"]
        assert len(games) > 0
        
        game = games[0]
        # Should have all required fields including colors
        assert "team1_color" in game
        assert "team2_color" in game
        assert "formatted" in game
        # Formatted should be exactly 20 characters (for use with 2 color tiles = 22 total)
        assert len(game["formatted"]) == 20
        # Colors should be in {CODE} format
        assert game["team1_color"].startswith("{") and game["team1_color"].endswith("}")
        assert game["team2_color"].startswith("{") and game["team2_color"].endswith("}")

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_data_with_cache(self, mock_get, sample_manifest, sample_config):
        """Test fetch_data uses cache when still fresh."""
        from datetime import datetime, timezone
        
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = sample_config
        
        cache_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        plugin._cache = {
            "games": [{"sport": "NFL", "team1": "Team A", "team2": "Team B"}],
            "last_updated": cache_time,
            "sport_count": 1,
            "game_count": 1
        }
        
        result = plugin.fetch_data()
        assert result.available is True
        assert mock_get.call_count == 0

    def test_fetch_data_no_api_key_uses_free(self, sample_manifest):
        """Test fetch_data uses free API key when none configured."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"sports": ["NFL"]}
        
        with patch.object(plugin, '_fetch_sport_scores', return_value=[]) as mock_fetch:
            plugin.fetch_data()
            assert mock_fetch.called
            call_args = mock_fetch.call_args
            assert call_args[0][2] == "123"

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_api_error(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores handles API errors."""
        mock_get.side_effect = Exception("API error")
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_empty_response(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores handles empty response."""
        mock_response = Mock()
        mock_response.json.return_value = {"events": None}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_api_key_fallback(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores falls back to free key on 402."""
        mock_response = Mock()
        mock_response.status_code = 402
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "paid_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_success(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league with successful response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "events": [
                {
                    "idEvent": "1",
                    "strEvent": "Team A vs Team B",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "intHomeScore": "24",
                    "intAwayScore": "17",
                    "strStatus": "Match Finished",
                    "dateEvent": "2024-01-15",
                    "strTime": "20:00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("test_key", 3)
        assert len(result) > 0

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_api_error(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league handles API errors."""
        mock_get.side_effect = Exception("API error")
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_no_events(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league with no events."""
        mock_response = Mock()
        mock_response.json.return_value = {"events": None}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("test_key", 3)
        assert result == []

    def test_abbreviate_team_name_short(self, sample_manifest):
        """Test _abbreviate_team_name with short name."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("SF", 10)
        assert result == "SF"

    def test_abbreviate_team_name_exact_length(self, sample_manifest):
        """Test _abbreviate_team_name with exact length match."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("12345", 5)
        assert result == "12345"

    def test_abbreviate_team_name_truncate(self, sample_manifest):
        """Test _abbreviate_team_name truncates long names."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("Very Long Team Name", 10)
        assert len(result) <= 10

    def test_abbreviate_team_name_with_city(self, sample_manifest):
        """Test _abbreviate_team_name removes city names."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("San Francisco 49ers", 10)
        assert "San Francisco" not in result

    def test_abbreviate_team_name_united(self, sample_manifest):
        """Test _abbreviate_team_name abbreviates 'United'."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("Manchester United", 10)
        assert len(result) <= 10

    def test_abbreviate_team_name_fc(self, sample_manifest):
        """Test _abbreviate_team_name abbreviates with FC."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("Liverpool FC", 10)
        assert len(result) <= 10

    def test_format_game_string_with_tie(self, sample_manifest):
        """Test _format_game_string with tied score."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._format_game_string("TeamA", "TeamB", 21, 21)
        assert len(result) == 22
        assert "21" in result

    def test_format_game_string_large_scores(self, sample_manifest):
        """Test _format_game_string with large scores."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._format_game_string("Team", "Team", 123, 456)
        assert len(result) == 22

    def test_format_game_string_custom_length(self, sample_manifest):
        """Test _format_game_string with custom max_length."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._format_game_string("A", "B", 1, 2, max_length=10)
        assert len(result) == 10

    def test_format_game_string_no_scores(self, sample_manifest):
        """Test _format_game_string with no scores uses '?'."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._format_game_string("TeamA", "TeamB", 0, 0)
        assert "?" in result

    def test_parse_event_missing_fields(self, sample_manifest):
        """Test _parse_event with missing required fields."""
        plugin = SportsScoresPlugin(sample_manifest)
        event = {
            "strHomeTeam": "TeamA",
        }
        result = plugin._parse_event(event, "NFL")
        assert result is None

    def test_parse_event_invalid_score(self, sample_manifest):
        """Test _parse_event with invalid score converts to 0."""
        plugin = SportsScoresPlugin(sample_manifest)
        event = {
            "strHomeTeam": "TeamA",
            "strAwayTeam": "TeamB",
            "intHomeScore": "not_a_number",
            "intAwayScore": "17"
        }
        result = plugin._parse_event(event, "NFL")
        assert result is not None
        assert result["score1"] == 0
        assert result["score2"] == 17

    def test_get_formatted_display_with_cache(self, sample_manifest):
        """Test get_formatted_display with cached data."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin._cache = {
            "games": [
                {
                    "sport": "NFL",
                    "team1": "SF",
                    "team2": "KC",
                    "team1_score": 24,
                    "team2_score": 21,
                    "team1_color": "{63}",
                    "team2_color": "{65}",
                    "formatted": "SF 24 - KC 21"
                }
            ]
        }
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6

    def test_get_formatted_display_no_cache(self, sample_manifest):
        """Test get_formatted_display without cache."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin._cache = None
        plugin.config = {}
        lines = plugin.get_formatted_display()
        assert lines is None

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_non_json_response(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores with non-JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_json_parse_error(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores with JSON parse error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_status_402_paid_key(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores handles 402 with paid key."""
        mock_response = Mock()
        mock_response.status_code = 402
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "paid_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_not_list(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores when events is not a list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"events": "not_a_list"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_status_not_200(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league with non-200 status."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_non_json(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league with non-JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_json_parse_error(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league with JSON parse error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_events_not_list(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league when events is not a list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"events": "not_a_list"}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_filters_zero_scores_free_api(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league filters zero scores with free API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "events": [
                {
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "intHomeScore": "0",
                    "intAwayScore": "0"
                },
                {
                    "strHomeTeam": "Team C",
                    "strAwayTeam": "Team D",
                    "intHomeScore": "24",
                    "intAwayScore": "17"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("123", 3)
        assert len(result) == 1
        assert result[0]["score1"] == 24

    def test_abbreviate_team_name_with_common_prefix(self, sample_manifest):
        """Test _abbreviate_team_name with FC/AC prefix."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("FC Barcelona", 8)
        assert len(result) <= 8
        assert "FC" in result

    def test_abbreviate_team_name_truncation(self, sample_manifest):
        """Test _abbreviate_team_name truncates when necessary."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("Very Long Team Name", 5)
        assert len(result) <= 5

    def test_fetch_data_unknown_sport_skipped(self, sample_manifest):
        """Test fetch_data skips unknown sports."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"sports": ["UnknownSport", "NFL"]}
        
        with patch.object(plugin, '_fetch_sport_scores', return_value=[{"sport": "NFL"}]):
            result = plugin.fetch_data()
            assert result.available
            assert plugin._fetch_sport_scores.call_count == 1

    def test_fetch_data_rate_limited_returns_cache(self, sample_manifest):
        """Test fetch_data returns cache when rate limited."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"sports": ["NFL", "NBA"]}
        plugin._cache = {
            "games": [{"sport": "NFL", "team1": "A", "team2": "B"}],
            "last_updated": "2024-01-01T00:00:00Z"
        }
        
        with patch.object(plugin, '_fetch_sport_scores', return_value=[]):
            result = plugin.fetch_data()
            assert result.available
            assert result.data == plugin._cache

    def test_fetch_data_no_games_with_cache(self, sample_manifest):
        """Test fetch_data returns cache when no new games found."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"sports": ["NFL"]}
        plugin._cache = {
            "games": [{"sport": "NFL", "team1": "A", "team2": "B"}],
            "last_updated": "2020-01-01T00:00:00Z"
        }
        
        with patch.object(plugin, '_fetch_sport_scores', return_value=[]):
            result = plugin.fetch_data()
            assert result.available

    def test_fetch_data_exception_with_cache(self, sample_manifest):
        """Test fetch_data returns cache on exception."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"sports": ["NFL"]}
        plugin._cache = {
            "games": [{"sport": "NFL"}],
            "last_updated": "2020-01-01T00:00:00Z"
        }
        
        with patch.object(plugin, '_fetch_sport_scores', side_effect=Exception("Test error")):
            result = plugin.fetch_data()
            assert result.available
            assert result.data == plugin._cache

    def test_fetch_data_exception_no_cache(self, sample_manifest):
        """Test fetch_data returns error when exception and no cache."""
        plugin = SportsScoresPlugin(sample_manifest)
        plugin.config = {"sports": ["NFL"]}
        plugin._cache = None
        
        with patch.object(plugin, '_fetch_sport_scores', side_effect=Exception("Test error")):
            result = plugin.fetch_data()
            assert not result.available

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_empty_response_text(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores with empty response text."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = ""
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_nfl_fallback_on_non_json(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores NFL fallback on non-JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html>Error</html>"
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        with patch.object(plugin, '_fetch_nfl_via_league', return_value=[{"sport": "NFL"}]):
            result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
            assert len(result) > 0

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_no_events_nfl_fallback(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores NFL fallback when no events."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        with patch.object(plugin, '_fetch_nfl_via_league', return_value=[{"sport": "NFL"}]):
            result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
            assert len(result) > 0

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_yesterday_fallback_nfl(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores uses yesterday fallback for NFL."""
        mock_response_today = Mock()
        mock_response_today.status_code = 200
        mock_response_today.headers = {"content-type": "application/json"}
        mock_response_today.json.return_value = {}
        
        mock_response_yesterday = Mock()
        mock_response_yesterday.status_code = 200
        mock_response_yesterday.json.return_value = {}
        
        mock_get.side_effect = [mock_response_today, mock_response_yesterday]
        
        plugin = SportsScoresPlugin(sample_manifest)
        with patch.object(plugin, '_fetch_nfl_via_league', return_value=[]):
            result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
            assert mock_get.call_count == 2

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_yesterday_json_error_nfl(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores handles yesterday JSON error for NFL."""
        mock_response_today = Mock()
        mock_response_today.status_code = 200
        mock_response_today.headers = {"content-type": "application/json"}
        mock_response_today.json.return_value = {}
        
        mock_response_yesterday = Mock()
        mock_response_yesterday.status_code = 200
        mock_response_yesterday.json.side_effect = ValueError("Invalid JSON")
        
        mock_get.side_effect = [mock_response_today, mock_response_yesterday]
        
        plugin = SportsScoresPlugin(sample_manifest)
        with patch.object(plugin, '_fetch_nfl_via_league', return_value=[]):
            result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
            assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_yesterday_not_200_nfl(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores handles yesterday non-200 for NFL."""
        mock_response_today = Mock()
        mock_response_today.status_code = 200
        mock_response_today.headers = {"content-type": "application/json"}
        mock_response_today.json.return_value = {}
        
        mock_response_yesterday = Mock()
        mock_response_yesterday.status_code = 500
        
        mock_get.side_effect = [mock_response_today, mock_response_yesterday]
        
        plugin = SportsScoresPlugin(sample_manifest)
        with patch.object(plugin, '_fetch_nfl_via_league', return_value=[]):
            result = plugin._fetch_sport_scores("NFL", "American%20Football", "test_key", 3)
            assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_sport_scores_no_events_non_nfl(self, mock_get, sample_manifest):
        """Test _fetch_sport_scores with no events for non-NFL sport."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_sport_scores("NBA", "Basketball", "test_key", 3)
        assert result == []

    @patch('plugins.sports_scores.requests.get')
    def test_fetch_nfl_via_league_free_api_filters_scores(self, mock_get, sample_manifest):
        """Test _fetch_nfl_via_league with free API filters and limits checks."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        events_list = []
        for i in range(50):
            events_list.append({
                "strHomeTeam": f"Team{i}A",
                "strAwayTeam": f"Team{i}B",
                "intHomeScore": "20",
                "intAwayScore": "10"
            })
        mock_response.json.return_value = {"events": events_list}
        mock_get.return_value = mock_response
        
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._fetch_nfl_via_league("123", 5)
        assert len(result) <= 5

    def test_abbreviate_team_name_acronym_generation(self, sample_manifest):
        """Test _abbreviate_team_name generates acronym for multi-word names."""
        plugin = SportsScoresPlugin(sample_manifest)
        result = plugin._abbreviate_team_name("New York Jets", 3)
        assert len(result) <= 3

    def test_parse_event_none_scores(self, sample_manifest):
        """Test _parse_event handles None scores."""
        plugin = SportsScoresPlugin(sample_manifest)
        event = {
            "strHomeTeam": "TeamA",
            "strAwayTeam": "TeamB",
            "intHomeScore": None,
            "intAwayScore": None
        }
        result = plugin._parse_event(event, "NFL")
        assert result is not None
        assert result["score1"] == 0
        assert result["score2"] == 0