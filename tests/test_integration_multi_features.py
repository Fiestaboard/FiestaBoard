"""Integration tests for multi-stop/route features."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.main import DisplayService
from src.pages.models import PageCreate
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.schedules.models import ScheduleCreate
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage
from src.settings.service import SettingsService
from src.templates.engine import TemplateEngine


class TestMuniIntegration:
    """Test MUNI multi-stop template integration."""

    def test_muni_indexed_variables(self):
        """Test that indexed MUNI variables work in templates."""
        engine = TemplateEngine()

        # Mock context with multiple stops
        context = {
            "muni": {
                "stops": [
                    {
                        "stop_code": "15726",
                        "line": "N-JUDAH",
                        "stop_name": "Church & Duboce",
                        "formatted": "N: 3, 8, 15 min",
                        "is_delayed": False,
                    },
                    {
                        "stop_code": "15727",
                        "line": "J-CHURCH",
                        "stop_name": "Market & Church",
                        "formatted": "J: 5, 12 min",
                        "is_delayed": True,
                    },
                ],
                "stop_count": 2,
                # Backward compatibility fields
                "line": "N-JUDAH",
                "stop_name": "Church & Duboce",
                "formatted": "N: 3, 8, 15 min",
            }
        }

        # Test indexed access
        result = engine.render("{{muni.stops.0.line}}", context)
        assert "N-JUDAH" in result

        result = engine.render("{{muni.stops.1.line}}", context)
        assert "J-CHURCH" in result

        # Test backward compatibility
        result = engine.render("{{muni.line}}", context)
        assert "N-JUDAH" in result

        # Test stop count
        result = engine.render("{{muni.stop_count}}", context)
        assert "2" in result

    def test_muni_multi_line_template(self):
        """Test rendering a multi-stop template."""
        engine = TemplateEngine()

        context = {
            "muni": {
                "stops": [{"line": "N", "formatted": "N: 3, 8 min"}, {"line": "J", "formatted": "J: 5, 12 min"}],
                "stop_count": 2,
            }
        }

        template = ["{center}MUNI ARRIVALS", "{{muni.stops.0.formatted}}", "{{muni.stops.1.formatted}}", "", "", ""]

        result = engine.render_lines(template, context)
        # render_lines returns a string with 6 lines joined by newlines
        lines = result.split("\n")
        assert len(lines) == 6
        assert "MUNI ARRIVALS" in lines[0]
        assert "N: 3, 8 min" in lines[1]
        assert "J: 5, 12 min" in lines[2]


class TestTrafficIntegration:
    """Test Traffic multi-route template integration."""

    def test_traffic_indexed_variables(self):
        """Test that indexed Traffic variables work in templates."""
        engine = TemplateEngine()

        # Mock context with multiple routes
        context = {
            "traffic": {
                "routes": [
                    {
                        "origin": "Home",
                        "destination": "Work",
                        "destination_name": "WORK",
                        "duration_minutes": 25,
                        "delay_minutes": 5,
                        "traffic_status": "MODERATE",
                        "formatted": "WORK: 25m (+5m)",
                    },
                    {
                        "origin": "Home",
                        "destination": "Airport",
                        "destination_name": "AIRPORT",
                        "duration_minutes": 45,
                        "delay_minutes": 0,
                        "traffic_status": "LIGHT",
                        "formatted": "AIRPORT: 45m",
                    },
                ],
                "route_count": 2,
                # Backward compatibility fields
                "duration_minutes": 25,
                "delay_minutes": 5,
                "traffic_status": "MODERATE",
                "destination_name": "WORK",
                "formatted": "WORK: 25m (+5m)",
            }
        }

        # Test indexed access
        result = engine.render("{{traffic.routes.0.destination_name}}", context)
        assert "WORK" in result

        result = engine.render("{{traffic.routes.1.destination_name}}", context)
        assert "AIRPORT" in result

        # Test backward compatibility
        result = engine.render("{{traffic.destination_name}}", context)
        assert "WORK" in result

        # Test route count
        result = engine.render("{{traffic.route_count}}", context)
        assert "2" in result

    def test_traffic_multi_line_template(self):
        """Test rendering a multi-route template."""
        engine = TemplateEngine()

        context = {
            "traffic": {
                "routes": [
                    {"destination_name": "WORK", "duration_minutes": 25, "formatted": "WORK: 25m (+5m)"},
                    {"destination_name": "AIRPORT", "duration_minutes": 45, "formatted": "AIRPORT: 45m"},
                ],
                "route_count": 2,
            }
        }

        template = [
            "{center}COMMUTE TIMES",
            "{{traffic.routes.0.formatted}}",
            "{{traffic.routes.1.formatted}}",
            "",
            "",
            "",
        ]

        result = engine.render_lines(template, context)
        # render_lines returns a string with 6 lines joined by newlines
        lines = result.split("\n")
        assert len(lines) == 6
        assert "COMMUTE TIMES" in lines[0]
        assert "WORK: 25m" in lines[1]
        assert "AIRPORT: 45m" in lines[2]


class TestBackwardCompatibility:
    """Test backward compatibility with old single-stop/route configs."""

    def test_muni_single_stop_still_works(self):
        """Test that old single stop config still works in templates."""
        engine = TemplateEngine()

        # Old format context (single stop at top level)
        context = {
            "muni": {
                "line": "N-JUDAH",
                "stop_name": "Church & Duboce",
                "formatted": "N: 3, 8, 15 min",
                "is_delayed": False,
            }
        }

        # Old template should still work
        result = engine.render("{{muni.line}}: {{muni.formatted}}", context)
        assert "N-JUDAH" in result
        assert "3, 8, 15 min" in result

    def test_traffic_single_route_still_works(self):
        """Test that old single route config still works in templates."""
        engine = TemplateEngine()

        # Old format context (single route at top level)
        context = {
            "traffic": {
                "destination_name": "DOWNTOWN",
                "duration_minutes": 25,
                "delay_minutes": 5,
                "traffic_status": "MODERATE",
                "formatted": "DOWNTOWN: 25m (+5m)",
            }
        }

        # Old template should still work
        result = engine.render("{{traffic.formatted}}", context)
        assert "DOWNTOWN: 25m" in result


class TestScheduleModeIntegration:
    """Test schedule mode integration with DisplayService."""

    @pytest.fixture
    def temp_files(self):
        """Create temporary storage files."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_pages.json") as pages_file:
            pages_path = pages_file.name
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_schedules.json") as schedules_file:
            schedules_path = schedules_file.name
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_settings.json") as settings_file:
            settings_path = settings_file.name

        yield {"pages": pages_path, "schedules": schedules_path, "settings": settings_path}

        # Cleanup
        Path(pages_path).unlink(missing_ok=True)
        Path(schedules_path).unlink(missing_ok=True)
        Path(settings_path).unlink(missing_ok=True)

    @pytest.fixture
    def services(self, temp_files):
        """Create service instances with temporary storage."""
        page_storage = PageStorage(storage_file=temp_files["pages"])
        page_service = PageService(storage=page_storage)

        schedule_storage = ScheduleStorage(storage_file=temp_files["schedules"])
        schedule_service = ScheduleService(storage=schedule_storage)

        settings_service = SettingsService(settings_file=temp_files["settings"])

        return {"page": page_service, "schedule": schedule_service, "settings": settings_service}

    def test_schedule_disabled_does_not_auto_push_active_page(self, services):
        """Regression for issue #970: schedule off must stop the polling-loop push.

        Pre-fix, toggling the schedule off fell back to "manual mode" and the
        polling loop kept pushing the manually-set active page (with its live
        variables, e.g. a clock) — overwriting out-of-band content sent from
        the Vestaboard app. Now schedule-off means "FiestaBoard stops touching
        the board" until the user explicitly re-enables the schedule or pushes
        a page via /settings/active-page or /settings/temporary-override.
        """
        page_service = services["page"]
        settings_service = services["settings"]

        # Create two pages
        page1 = page_service.create_page(
            PageCreate(name="Manual Page", type="template", template=["Manual Active Page", "", "", "", "", ""])
        )
        page_service.create_page(
            PageCreate(name="Scheduled Page", type="template", template=["This is scheduled", "", "", "", "", ""])
        )

        # Set manual active page
        settings_service.set_active_page_id(page1.id)

        # Ensure schedule mode is disabled (default)
        assert not settings_service.is_schedule_enabled()

        # Create a DisplayService instance with mocked board client
        with patch("src.main.BoardClient") as mock_board_client:
            mock_client_instance = Mock()
            mock_client_instance.read_current_message.return_value = None
            mock_client_instance.send_characters.return_value = (True, True)
            mock_board_client.return_value = mock_client_instance

            with patch("src.main.get_page_service", return_value=page_service):
                with patch("src.main.get_settings_service", return_value=settings_service):
                    with patch("src.main.get_schedule_service", return_value=services["schedule"]):
                        service = DisplayService()
                        service.vb_client = mock_client_instance

                        # Tick the polling loop.
                        sent = service.check_and_send_active_page()

                        # The polling tick must be a no-op when schedule is off.
                        assert sent is False
                        assert service._last_active_page_id is None
                        mock_client_instance.send_characters.assert_not_called()

    def test_schedule_mode_uses_scheduled_page(self, services):
        """Test that schedule mode uses the schedule-based page selection."""
        page_service = services["page"]
        schedule_service = services["schedule"]
        settings_service = services["settings"]

        # Create two pages
        page1 = page_service.create_page(
            PageCreate(name="Manual Page", type="template", template=["Manual Active Page", "", "", "", "", ""])
        )
        page2 = page_service.create_page(
            PageCreate(name="Scheduled Page", type="template", template=["This is scheduled", "", "", "", "", ""])
        )

        # Set manual active page to page1
        settings_service.set_active_page_id(page1.id)

        # Create a schedule for page2 (Monday 9am-5pm)
        schedule_service.create_schedule(
            ScheduleCreate(
                page_id=page2.id,
                start_time="09:00",
                end_time="17:00",
                day_pattern="custom",
                custom_days=["monday"],
                enabled=True,
            )
        )

        # Enable schedule mode
        settings_service.set_schedule_enabled(True)

        # Create a DisplayService instance with mocked board client
        with patch("src.main.BoardClient") as mock_board_client:
            mock_client_instance = Mock()
            mock_client_instance.read_current_message.return_value = None
            mock_client_instance.send_characters.return_value = (True, True)
            mock_board_client.return_value = mock_client_instance

            with patch("src.main.get_page_service", return_value=page_service):
                with patch("src.main.get_settings_service", return_value=settings_service):
                    with patch("src.main.get_schedule_service", return_value=schedule_service):
                        with patch("src.schedules.service.get_settings_service", return_value=settings_service):
                            # Mock TimeService to return Monday 12:00 (within schedule)
                            # Create a mock datetime for Monday 12:00
                            mock_datetime_obj = datetime(2025, 1, 13, 12, 0, 0)  # Monday Jan 13, 2025 at 12:00
                            mock_datetime_obj = mock_datetime_obj.replace(tzinfo=UTC)

                            mock_time_service = Mock()
                            mock_time_service.get_current_time.return_value = mock_datetime_obj

                            with patch("src.time_service.get_time_service", return_value=mock_time_service):
                                service = DisplayService()
                                service.vb_client = mock_client_instance

                                # Check active page (should use scheduled page2, not manual page1)
                                service.check_and_send_active_page()

                                # Verify it used page2 (scheduled), not page1 (manual)
                                assert service._last_active_page_id == page2.id

    def test_schedule_mode_with_no_match_uses_default(self, services):
        """Test that schedule mode uses default page when no schedule matches."""
        page_service = services["page"]
        schedule_service = services["schedule"]
        settings_service = services["settings"]

        # Create pages
        default_page = page_service.create_page(
            PageCreate(name="Default Page", type="template", template=["Default for gaps", "", "", "", "", ""])
        )
        scheduled_page = page_service.create_page(
            PageCreate(name="Scheduled Page", type="template", template=["Scheduled content", "", "", "", "", ""])
        )

        # Set default page in schedules
        schedule_service.set_default_page(default_page.id)

        # Create a schedule for Monday 9am-5pm only
        schedule_service.create_schedule(
            ScheduleCreate(
                page_id=scheduled_page.id,
                start_time="09:00",
                end_time="17:00",
                day_pattern="custom",
                custom_days=["monday"],
                enabled=True,
            )
        )

        # Enable schedule mode
        settings_service.set_schedule_enabled(True)

        # Create a DisplayService instance with mocked board client
        with patch("src.main.BoardClient") as mock_board_client:
            mock_client_instance = Mock()
            mock_client_instance.read_current_message.return_value = None
            mock_client_instance.send_characters.return_value = (True, True)
            mock_board_client.return_value = mock_client_instance

            with patch("src.main.get_page_service", return_value=page_service):
                with patch("src.main.get_settings_service", return_value=settings_service):
                    with patch("src.main.get_schedule_service", return_value=schedule_service):
                        with patch("src.schedules.service.get_settings_service", return_value=settings_service):
                            # Mock TimeService to return Monday 20:00 (outside schedule, should use default)
                            # Create a mock datetime for Monday 20:00
                            mock_datetime_obj = datetime(2025, 1, 13, 20, 0, 0)  # Monday Jan 13, 2025 at 20:00
                            mock_datetime_obj = mock_datetime_obj.replace(tzinfo=UTC)

                            mock_time_service = Mock()
                            mock_time_service.get_current_time.return_value = mock_datetime_obj

                            with patch("src.time_service.get_time_service", return_value=mock_time_service):
                                service = DisplayService()
                                service.vb_client = mock_client_instance

                                # Check active page (should use default page)
                                service.check_and_send_active_page()

                                # Verify it used the default page
                                assert service._last_active_page_id == default_page.id

    def test_schedule_mode_with_no_match_and_no_default(self, services):
        """Test that schedule mode returns False when no match and no default."""
        page_service = services["page"]
        schedule_service = services["schedule"]
        settings_service = services["settings"]

        # Create a scheduled page
        scheduled_page = page_service.create_page(
            PageCreate(name="Scheduled Page", type="template", template=["Scheduled content", "", "", "", "", ""])
        )

        # Create a schedule for Monday 9am-5pm only
        schedule_service.create_schedule(
            ScheduleCreate(
                page_id=scheduled_page.id,
                start_time="09:00",
                end_time="17:00",
                day_pattern="custom",
                custom_days=["monday"],
                enabled=True,
            )
        )

        # DO NOT set a default page

        # Enable schedule mode
        settings_service.set_schedule_enabled(True)

        # Create a DisplayService instance with mocked board client
        with patch("src.main.BoardClient") as mock_board_client:
            mock_client_instance = Mock()
            mock_client_instance.read_current_message.return_value = None
            mock_board_client.return_value = mock_client_instance

            with patch("src.main.get_page_service", return_value=page_service):
                with patch("src.main.get_settings_service", return_value=settings_service):
                    with patch("src.main.get_schedule_service", return_value=schedule_service):
                        with patch("src.schedules.service.get_settings_service", return_value=settings_service):
                            # Mock TimeService to return Tuesday 12:00 (no schedule for Tuesday)
                            # Create a mock datetime for Tuesday 12:00
                            mock_datetime_obj = datetime(2025, 1, 14, 12, 0, 0)  # Tuesday Jan 14, 2025 at 12:00
                            mock_datetime_obj = mock_datetime_obj.replace(tzinfo=UTC)

                            mock_time_service = Mock()
                            mock_time_service.get_current_time.return_value = mock_datetime_obj

                            with patch("src.time_service.get_time_service", return_value=mock_time_service):
                                service = DisplayService()
                                service.vb_client = mock_client_instance

                                # Check active page (should return False - no page available)
                                result = service.check_and_send_active_page()

                                # Verify it returned False and didn't send
                                assert result is False
                                assert service._last_active_page_id is None
