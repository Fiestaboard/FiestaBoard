"""Tests for Config.SILENCE_SCHEDULE_* class properties.

These properties read from `config_manager.get_feature("silence_schedule")`
and apply normalization (defaults, validation, uppercasing). They are the
single source of truth used by DisplayService at render time.
"""
from unittest.mock import patch

import pytest

from src.config import Config


def _patch_feature(feature_dict):
    """Patch Config._get_feature to return the given silence_schedule dict."""
    return patch.object(Config, "_get_feature", classmethod(lambda cls, name: feature_dict))


class TestSilenceScheduleMode:
    def test_default_is_freeze_when_missing(self):
        with _patch_feature({}):
            assert Config.SILENCE_SCHEDULE_MODE == "freeze"

    @pytest.mark.parametrize("mode", ["indicator", "freeze", "page"])
    def test_accepts_valid_modes(self, mode):
        with _patch_feature({"mode": mode}):
            assert Config.SILENCE_SCHEDULE_MODE == mode

    @pytest.mark.parametrize("bad", ["", "garbage", "INDICATOR", None, 42])
    def test_invalid_falls_back_to_freeze(self, bad):
        with _patch_feature({"mode": bad}):
            assert Config.SILENCE_SCHEDULE_MODE == "freeze"


class TestSilenceScheduleIndicatorText:
    def test_default_is_snoozing_when_missing(self):
        with _patch_feature({}):
            assert Config.SILENCE_SCHEDULE_INDICATOR_TEXT == "SNOOZING"

    def test_lowercase_is_uppercased(self):
        with _patch_feature({"indicator_text": "bedtime"}):
            assert Config.SILENCE_SCHEDULE_INDICATOR_TEXT == "BEDTIME"

    def test_whitespace_is_stripped(self):
        with _patch_feature({"indicator_text": "  hush  "}):
            assert Config.SILENCE_SCHEDULE_INDICATOR_TEXT == "HUSH"

    @pytest.mark.parametrize("bad", ["", "   ", None, 42, []])
    def test_invalid_falls_back_to_default(self, bad):
        with _patch_feature({"indicator_text": bad}):
            assert Config.SILENCE_SCHEDULE_INDICATOR_TEXT == "SNOOZING"


class TestSilenceScheduleIndicatorPosition:
    def test_default_is_center_when_missing(self):
        with _patch_feature({}):
            assert Config.SILENCE_SCHEDULE_INDICATOR_POSITION == "center"

    @pytest.mark.parametrize(
        "pos",
        ["center", "top-left", "top-right", "bottom-left", "bottom-right"],
    )
    def test_accepts_each_valid_position(self, pos):
        with _patch_feature({"indicator_position": pos}):
            assert Config.SILENCE_SCHEDULE_INDICATOR_POSITION == pos

    @pytest.mark.parametrize("bad", ["", "middle", "TOP-LEFT", None, 42])
    def test_invalid_falls_back_to_center(self, bad):
        with _patch_feature({"indicator_position": bad}):
            assert Config.SILENCE_SCHEDULE_INDICATOR_POSITION == "center"


class TestSilenceSchedulePageId:
    def test_missing_returns_none(self):
        with _patch_feature({}):
            assert Config.SILENCE_SCHEDULE_PAGE_ID is None

    def test_valid_string_returned(self):
        with _patch_feature({"page_id": "page-abc"}):
            assert Config.SILENCE_SCHEDULE_PAGE_ID == "page-abc"

    @pytest.mark.parametrize("bad", ["", "   ", None, 0, 42, []])
    def test_invalid_returns_none(self, bad):
        with _patch_feature({"page_id": bad}):
            assert Config.SILENCE_SCHEDULE_PAGE_ID is None
