"""Tests for TimeService."""

import pytest
from datetime import datetime, time
from unittest.mock import Mock, patch
import pytz

from src.time_service import TimeService, get_time_service, reset_time_service


class TestTimeServiceCore:
    """Tests for core time operations."""
    
    def test_get_current_utc(self):
        """Test get_current_utc returns UTC datetime."""
        service = TimeService()
        utc_now = service.get_current_utc()
        
        assert utc_now.tzinfo == pytz.UTC
        assert isinstance(utc_now, datetime)
    
    def test_get_current_time_default_timezone(self):
        """Test get_current_time with default timezone."""
        service = TimeService(default_timezone="America/Los_Angeles")
        pst_now = service.get_current_time()
        
        assert pst_now.tzinfo is not None
        assert isinstance(pst_now, datetime)
    
    def test_get_current_time_specified_timezone(self):
        """Test get_current_time with specified timezone."""
        service = TimeService()
        est_now = service.get_current_time("America/New_York")
        
        assert est_now.tzinfo is not None
        assert isinstance(est_now, datetime)
    
    def test_get_current_time_invalid_timezone_uses_default(self):
        """Test get_current_time with invalid timezone falls back to default."""
        service = TimeService(default_timezone="America/Los_Angeles")
        result = service.get_current_time("Invalid/Timezone")
        
        assert result.tzinfo is not None  # Should still return something


class TestTimeServiceSilenceMode:
    """Tests for silence mode time window checking."""
    
    def test_is_time_in_window_same_day_inside(self):
        """Test time window check for same-day window, time inside."""
        service = TimeService()
        
        # Mock get_current_utc to return 12:00 UTC
        with patch.object(service, 'get_current_utc') as mock_get_utc:
            mock_get_utc.return_value = datetime(2024, 1, 15, 12, 0, tzinfo=pytz.UTC)
            
            # Window: 10:00 UTC to 14:00 UTC
            result = service.is_time_in_window("10:00+00:00", "14:00+00:00")
            
            assert result is True
    
    def test_is_time_in_window_same_day_outside(self):
        """Test time window check for same-day window, time outside."""
        service = TimeService()
        
        # Mock get_current_utc to return 15:00 UTC
        with patch.object(service, 'get_current_utc') as mock_get_utc:
            mock_get_utc.return_value = datetime(2024, 1, 15, 15, 0, tzinfo=pytz.UTC)
            
            # Window: 10:00 UTC to 14:00 UTC
            result = service.is_time_in_window("10:00+00:00", "14:00+00:00")
            
            assert result is False
    
    def test_is_time_in_window_midnight_spanning_before_midnight(self):
        """Test midnight-spanning window, current time before midnight."""
        service = TimeService()
        
        # Mock get_current_utc to return 22:00 UTC
        with patch.object(service, 'get_current_utc') as mock_get_utc:
            mock_get_utc.return_value = datetime(2024, 1, 15, 22, 0, tzinfo=pytz.UTC)
            
            # Window: 20:00 UTC to 08:00 UTC (spans midnight)
            result = service.is_time_in_window("20:00+00:00", "08:00+00:00")
            
            assert result is True
    
    def test_is_time_in_window_midnight_spanning_after_midnight(self):
        """Test midnight-spanning window, current time after midnight."""
        service = TimeService()
        
        # Mock get_current_utc to return 06:00 UTC
        with patch.object(service, 'get_current_utc') as mock_get_utc:
            mock_get_utc.return_value = datetime(2024, 1, 15, 6, 0, tzinfo=pytz.UTC)
            
            # Window: 20:00 UTC to 08:00 UTC (spans midnight)
            result = service.is_time_in_window("20:00+00:00", "08:00+00:00")
            
            assert result is True
    
    def test_is_time_in_window_midnight_spanning_outside(self):
        """Test midnight-spanning window, current time outside."""
        service = TimeService()
        
        # Mock get_current_utc to return 12:00 UTC
        with patch.object(service, 'get_current_utc') as mock_get_utc:
            mock_get_utc.return_value = datetime(2024, 1, 15, 12, 0, tzinfo=pytz.UTC)
            
            # Window: 20:00 UTC to 08:00 UTC (spans midnight)
            result = service.is_time_in_window("20:00+00:00", "08:00+00:00")
            
            assert result is False
    
    def test_is_time_in_window_invalid_format_returns_false(self):
        """Test invalid time format returns False."""
        service = TimeService()
        
        result = service.is_time_in_window("invalid", "14:00+00:00")
        
        assert result is False


class TestTimeServiceConversions:
    """Tests for timezone conversion functions."""
    
    def test_local_to_utc_iso_pst(self):
        """Test converting PST local time to UTC ISO."""
        service = TimeService()
        
        # 20:00 PST (UTC-8 in winter) = 04:00 UTC next day
        result = service.local_to_utc_iso("20:00", "America/Los_Angeles")
        
        # Result should be in UTC format (time only, not date-dependent in this test)
        assert "+00:00" in result
        assert ":" in result
    
    def test_local_to_utc_iso_est(self):
        """Test converting EST local time to UTC ISO."""
        service = TimeService()
        
        # 20:00 EST (UTC-5 in winter) = 01:00 UTC next day
        result = service.local_to_utc_iso("20:00", "America/New_York")
        
        assert "+00:00" in result
        assert ":" in result
    
    def test_utc_iso_to_local_pst(self):
        """Test converting UTC ISO to PST local time."""
        service = TimeService()
        
        # 04:00 UTC = 20:00 PST (UTC-8 in winter)
        result = service.utc_iso_to_local("04:00+00:00", "America/Los_Angeles")
        
        # Should return local time format
        assert ":" in result
        assert len(result) == 5  # HH:MM format
    
    def test_utc_iso_to_local_invalid_timezone_uses_utc(self):
        """Test invalid timezone falls back to UTC."""
        service = TimeService()
        
        result = service.utc_iso_to_local("12:00+00:00", "Invalid/Timezone")
        
        # Should still return a valid time
        assert ":" in result
    
    def test_local_to_utc_iso_invalid_time_returns_default(self):
        """Test invalid time format returns default."""
        service = TimeService()
        
        result = service.local_to_utc_iso("invalid", "America/Los_Angeles")
        
        assert result == "00:00+00:00"


class TestTimeServiceTimestamps:
    """Tests for timestamp generation and formatting."""
    
    def test_create_utc_timestamp(self):
        """Test creating UTC timestamp."""
        service = TimeService()
        
        timestamp = service.create_utc_timestamp()
        
        # Should be ISO format with timezone
        assert "T" in timestamp  # ISO format separator
        assert "+" in timestamp or "Z" in timestamp or timestamp.endswith("+00:00")
    
    def test_format_timestamp_local_pst(self):
        """Test formatting UTC timestamp to PST."""
        service = TimeService()
        
        # Create a UTC timestamp
        utc_timestamp = "2025-12-26T22:30:00+00:00"
        
        result = service.format_timestamp_local(utc_timestamp, "America/Los_Angeles")
        
        # Should contain date, time, and timezone abbreviation
        assert "2025" in result
        assert ":" in result
        # Should have timezone info (PST or PDT depending on DST)
        assert any(tz in result for tz in ["PST", "PDT", "P"])
    
    def test_format_timestamp_local_invalid_timestamp_returns_original(self):
        """Test invalid timestamp returns original string."""
        service = TimeService()
        
        invalid_timestamp = "not-a-timestamp"
        result = service.format_timestamp_local(invalid_timestamp, "America/Los_Angeles")
        
        assert result == invalid_timestamp


class TestTimeServiceParseIsoTime:
    """Tests for ISO time parsing."""
    
    def test_parse_iso_time_utc(self):
        """Test parsing UTC time."""
        service = TimeService()
        
        result = service.parse_iso_time("12:00+00:00")
        
        assert result is not None
        assert isinstance(result, datetime)
        assert result.tzinfo == pytz.UTC
    
    def test_parse_iso_time_with_negative_offset(self):
        """Test parsing time with negative offset (e.g., PST)."""
        service = TimeService()
        
        result = service.parse_iso_time("20:00-08:00")
        
        assert result is not None
        assert isinstance(result, datetime)
    
    def test_parse_iso_time_with_positive_offset(self):
        """Test parsing time with positive offset (e.g., CET)."""
        service = TimeService()
        
        result = service.parse_iso_time("14:00+01:00")
        
        assert result is not None
        assert isinstance(result, datetime)
    
    def test_parse_iso_time_invalid_format_returns_none(self):
        """Test invalid format returns None."""
        service = TimeService()
        
        result = service.parse_iso_time("invalid")
        
        assert result is None
    
    def test_parse_iso_time_short_format_returns_none(self):
        """Test short format (old HH:MM) returns None."""
        service = TimeService()
        
        result = service.parse_iso_time("12:00")
        
        assert result is None


class TestTimeServiceSingleton:
    """Tests for singleton pattern."""
    
    def test_get_time_service_returns_singleton(self):
        """Test get_time_service returns same instance."""
        reset_time_service()  # Reset first
        
        service1 = get_time_service()
        service2 = get_time_service()
        
        assert service1 is service2
    
    def test_reset_time_service(self):
        """Test reset_time_service creates new instance."""
        service1 = get_time_service()
        reset_time_service()
        service2 = get_time_service()
        
        assert service1 is not service2


class TestTimeServiceInitialization:
    """Tests for TimeService initialization."""
    
    def test_init_with_valid_timezone(self):
        """Test initialization with valid timezone."""
        service = TimeService(default_timezone="America/New_York")
        
        assert service.default_timezone == "America/New_York"
    
    def test_init_with_invalid_timezone_falls_back_to_utc(self):
        """Test initialization with invalid timezone falls back to UTC."""
        service = TimeService(default_timezone="Invalid/Timezone")
        
        # Should still initialize, using UTC as fallback
        assert service._default_tz == pytz.UTC


class TestParseIsoTimeErrorHandling:
    """Tests for parse_iso_time ValueError/IndexError paths (lines 118-120)."""

    def test_parse_iso_time_malformed_offset_raises_value_error(self):
        """String long enough but offset portion is unparseable."""
        service = TimeService()
        # 11+ chars but offset part "XABCDE" can't be split/converted to int
        result = service.parse_iso_time("12:00XABCDE")
        assert result is None

    def test_parse_iso_time_non_numeric_time_part(self):
        """Time part contains non-numeric characters causing ValueError."""
        service = TimeService()
        result = service.parse_iso_time("AB:CD+00:00")
        assert result is None

    def test_parse_iso_time_missing_colon_in_offset(self):
        """Offset missing colon triggers IndexError/ValueError."""
        service = TimeService()
        result = service.parse_iso_time("12:00+0000X")
        assert result is None


class TestLocalToUtcIsoEdgeCases:
    """Tests for local_to_utc_iso edge cases."""

    def test_missing_local_time_returns_default(self):
        """Empty local_time returns default (lines 167-168)."""
        service = TimeService()
        assert service.local_to_utc_iso("", "America/Los_Angeles") == "00:00+00:00"

    def test_missing_timezone_returns_default(self):
        """Empty timezone returns default (lines 167-168)."""
        service = TimeService()
        assert service.local_to_utc_iso("20:00", "") == "00:00+00:00"

    def test_unknown_timezone_falls_back_to_utc(self):
        """Unknown timezone uses UTC fallback (lines 172-174)."""
        service = TimeService()
        result = service.local_to_utc_iso("12:00", "Fake/Zone")
        assert "+00:00" in result
        # 12:00 UTC -> 12:00 UTC when fallback is UTC
        assert result == "12:00+00:00"

    def test_wrong_number_of_parts_returns_default(self):
        """Time with extra colons raises ValueError (line 183)."""
        service = TimeService()
        assert service.local_to_utc_iso("12:00:00", "America/Los_Angeles") == "00:00+00:00"

    def test_hour_out_of_range_returns_default(self):
        """Hour > 23 raises ValueError (line 189)."""
        service = TimeService()
        assert service.local_to_utc_iso("25:00", "America/Los_Angeles") == "00:00+00:00"

    def test_minute_out_of_range_returns_default(self):
        """Minute > 59 raises ValueError (line 191)."""
        service = TimeService()
        assert service.local_to_utc_iso("12:99", "America/Los_Angeles") == "00:00+00:00"


class TestUtcIsoToLocalEdgeCases:
    """Tests for utc_iso_to_local edge cases."""

    def test_missing_utc_iso_returns_default(self):
        """Empty utc_iso returns default (lines 221-222)."""
        service = TimeService()
        assert service.utc_iso_to_local("", "America/Los_Angeles") == "00:00"

    def test_missing_timezone_returns_default(self):
        """Empty timezone returns default (lines 221-222)."""
        service = TimeService()
        assert service.utc_iso_to_local("04:00+00:00", "") == "00:00"

    def test_unknown_timezone_falls_back_to_utc(self):
        """Unknown timezone uses UTC fallback (lines 232-233 for tz resolution)."""
        service = TimeService()
        result = service.utc_iso_to_local("12:00+00:00", "Fake/Zone")
        assert result == "12:00"

    def test_unparseable_utc_iso_returns_default(self):
        """parse_iso_time returns None -> default (lines 232-233)."""
        service = TimeService()
        assert service.utc_iso_to_local("bad", "America/Los_Angeles") == "00:00"

    def test_conversion_exception_returns_default(self):
        """Exception during astimezone returns default (lines 239-241)."""
        service = TimeService()
        with patch.object(service, 'parse_iso_time') as mock_parse:
            mock_dt = Mock()
            mock_dt.astimezone.side_effect = Exception("conversion error")
            mock_parse.return_value = mock_dt
            assert service.utc_iso_to_local("12:00+00:00", "America/Los_Angeles") == "00:00"


class TestFormatTimestampLocalEdgeCases:
    """Tests for format_timestamp_local edge cases."""

    def test_naive_timestamp_gets_localized(self):
        """Naive datetime (no tzinfo) gets UTC localized (line 270)."""
        service = TimeService()
        # Timestamp without offset -> parsed as naive
        result = service.format_timestamp_local("2025-06-15T12:00:00", "America/Los_Angeles")
        assert "2025" in result
        assert ":" in result

    def test_unknown_timezone_falls_back_to_utc(self):
        """Unknown timezone uses UTC fallback (lines 275-277)."""
        service = TimeService()
        result = service.format_timestamp_local("2025-06-15T12:00:00+00:00", "Fake/Zone")
        assert "2025" in result
        assert "UTC" in result

