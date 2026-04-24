from datetime import date, datetime

import pytest

from wodplanner.utils.dates import (
    fmt_api_datetime,
    parse_api_datetime,
    parse_iso_date,
    parse_iso_datetime,
)


class TestParseIsoDate:
    def test_valid_iso_date(self):
        result = parse_iso_date("2026-04-23")
        assert result == date(2026, 4, 23)

    def test_valid_iso_date_with_time_ignored(self):
        result = parse_iso_date("2026-04-23")
        assert result == date(2026, 4, 23)

    def test_invalid_iso_date_raises(self):
        with pytest.raises(ValueError):
            parse_iso_date("not-a-date")


class TestParseIsoDatetime:
    def test_valid_iso_datetime(self):
        result = parse_iso_datetime("2026-04-23T10:30:00")
        assert result == datetime(2026, 4, 23, 10, 30, 0)

    def test_valid_iso_datetime_with_microseconds(self):
        result = parse_iso_datetime("2026-04-23T10:30:00.123456")
        assert result == datetime(2026, 4, 23, 10, 30, 0, 123456)

    def test_invalid_iso_datetime_raises(self):
        with pytest.raises(ValueError):
            parse_iso_datetime("not-a-datetime")


class TestParseApiDatetime:
    def test_valid_api_datetime(self):
        result = parse_api_datetime("2026-04-23 10:30")
        assert result == datetime(2026, 4, 23, 10, 30)

    def test_valid_api_datetime_midnight(self):
        result = parse_api_datetime("2026-04-23 00:00")
        assert result == datetime(2026, 4, 23, 0, 0)

    def test_invalid_api_datetime_raises(self):
        with pytest.raises(ValueError):
            parse_api_datetime("not-a-datetime")


class TestFmtApiDatetime:
    def test_fmt_api_datetime(self):
        dt = datetime(2026, 4, 23, 10, 30)
        result = fmt_api_datetime(dt)
        assert result == "2026-04-23 10:30"

    def test_fmt_api_datetime_midnight(self):
        dt = datetime(2026, 4, 23, 0, 0)
        result = fmt_api_datetime(dt)
        assert result == "2026-04-23 00:00"

    def test_roundtrip(self):
        original = "2026-04-23 14:45"
        dt = parse_api_datetime(original)
        result = fmt_api_datetime(dt)
        assert result == original