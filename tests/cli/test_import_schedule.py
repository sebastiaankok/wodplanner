from datetime import date
from unittest.mock import MagicMock, patch

from wodplanner.cli.import_schedule import (
    append_content,
    clean_text,
    extract_schedules_from_pdf,
    is_class_name,
    is_continuation_row,
    is_date_row,
    parse_dutch_date,
)


class TestParseDutchDate:
    def test_valid_date(self):
        assert parse_dutch_date("Maandag 13 April", 2026) == date(2026, 4, 13)

    def test_case_insensitive(self):
        assert parse_dutch_date("maandag 5 januari", 2026) == date(2026, 1, 5)

    def test_unknown_month_returns_none(self):
        assert parse_dutch_date("Maandag 5 Unknown", 2026) is None

    def test_no_match_returns_none(self):
        assert parse_dutch_date("not a date", 2026) is None

    def test_invalid_day_returns_none(self):
        assert parse_dutch_date("Maandag 32 januari", 2026) is None

    def test_all_dutch_weekday_prefixes(self):
        for day in ("Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"):
            assert parse_dutch_date(f"{day} 1 januari", 2026) == date(2026, 1, 1)

    def test_all_dutch_months(self):
        months = {
            "januari": 1, "februari": 2, "maart": 3, "april": 4,
            "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
            "september": 9, "oktober": 10, "november": 11, "december": 12,
        }
        for name, num in months.items():
            d = parse_dutch_date(f"Maandag 1 {name}", 2026)
            assert d is not None and d.month == num


class TestIsDateRow:
    def test_valid_date_row(self):
        assert is_date_row("Maandag 13 April") is True

    def test_empty_string(self):
        assert is_date_row("") is False

    def test_class_name_not_date(self):
        assert is_date_row("CrossFit") is False

    def test_with_extra_whitespace(self):
        assert is_date_row("  Vrijdag 5 maart  ") is True

    def test_all_weekdays_match(self):
        for day in ("Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"):
            assert is_date_row(f"{day} 1 Januari") is True


class TestIsClassName:
    def test_crossfit(self):
        assert is_class_name("CrossFit") is True

    def test_cf101(self):
        assert is_class_name("CF101") is True

    def test_gymnastics(self):
        assert is_class_name("Gymnastics") is True

    def test_olympic_lifting(self):
        assert is_class_name("Olympic Lifting") is True

    def test_strongman(self):
        assert is_class_name("Strongman") is True

    def test_teen_athlete(self):
        assert is_class_name("Teen Athlete") is True

    def test_hycross(self):
        assert is_class_name("HyCross") is True

    def test_unknown(self):
        assert is_class_name("Something Random") is False

    def test_empty(self):
        assert is_class_name("") is False


class TestCleanText:
    def test_none_returns_none(self):
        assert clean_text(None) is None

    def test_empty_returns_none(self):
        assert clean_text("") is None

    def test_collapses_whitespace(self):
        assert clean_text("hello   world") == "hello world"

    def test_strips_leading_trailing(self):
        assert clean_text("  hello  ") == "hello"

    def test_unclosed_paren_merges_next_line(self):
        assert clean_text("(first part\ncontinued)") == "(first part continued)"

    def test_closed_paren_keeps_lines(self):
        result = clean_text("(done)\nnext line")
        assert result == "(done)\nnext line"

    def test_whitespace_only_returns_none(self):
        assert clean_text("   \n  ") is None


class TestAppendContent:
    def test_both_none(self):
        assert append_content(None, None) is None

    def test_existing_none(self):
        assert append_content(None, "new") == "new"

    def test_new_none(self):
        assert append_content("existing", None) == "existing"

    def test_both_present(self):
        assert append_content("a", "b") == "a\nb"


class TestIsContinuationRow:
    def test_none_first_content_later(self):
        assert is_continuation_row([None, "content"]) is True

    def test_empty_first_data_later(self):
        assert is_continuation_row(["", "  data  "]) is True

    def test_first_has_content(self):
        assert is_continuation_row(["CrossFit", "workout"]) is False

    def test_all_empty(self):
        assert is_continuation_row([None, None, ""]) is False

    def test_empty_row(self):
        assert is_continuation_row([]) is False


class TestExtractSchedulesFromPdf:
    def _mock_pdf(self, tables_per_page):
        pages = []
        for tables in tables_per_page:
            page = MagicMock()
            page.extract_tables.return_value = tables
            pages.append(page)
        pdf = MagicMock()
        pdf.__enter__ = MagicMock(return_value=pdf)
        pdf.__exit__ = MagicMock(return_value=False)
        pdf.pages = pages
        return pdf

    def test_empty_pdf_returns_empty(self, tmp_path):
        pdf = self._mock_pdf([[]])
        with patch("pdfplumber.open", return_value=pdf):
            result = extract_schedules_from_pdf(tmp_path / "empty.pdf", 2026)
        assert result == []

    def test_single_class_entry(self, tmp_path):
        table = [
            ["Maandag 14 April", None, None, None],
            ["CrossFit", "Rowing warmup", "Back Squat 5x5", "21-15-9 Thrusters"],
        ]
        with patch("pdfplumber.open", return_value=self._mock_pdf([[table]])):
            result = extract_schedules_from_pdf(tmp_path / "test.pdf", 2026)

        assert len(result) == 1
        assert result[0].date == date(2026, 4, 14)
        assert result[0].class_type == "CrossFit"
        assert result[0].warmup_mobility == "Rowing warmup"
        assert result[0].strength_specialty == "Back Squat 5x5"
        assert result[0].metcon == "21-15-9 Thrusters"

    def test_skips_header_rows(self, tmp_path):
        table = [
            ["Maandag 14 April", None, None, None],
            ["datum", "warming-up & mobility", "strength", "metcon"],
            ["CrossFit", "warmup", "strength", "metcon content"],
        ]
        with patch("pdfplumber.open", return_value=self._mock_pdf([[table]])):
            result = extract_schedules_from_pdf(tmp_path / "test.pdf", 2026)
        assert len(result) == 1

    def test_continuation_row_appends(self, tmp_path):
        table = [
            ["Maandag 14 April", None, None, None],
            ["CrossFit", "Warmup part 1", "Squat", "Row 500m"],
            [None, "Warmup part 2", None, None],
        ]
        with patch("pdfplumber.open", return_value=self._mock_pdf([[table]])):
            result = extract_schedules_from_pdf(tmp_path / "test.pdf", 2026)

        assert len(result) == 1
        assert "Warmup part 2" in result[0].warmup_mobility

    def test_multiple_classes_same_day(self, tmp_path):
        table = [
            ["Maandag 14 April", None, None, None],
            ["CrossFit", "w1", "s1", "m1"],
            ["Gymnastics", "w2", "s2", "m2"],
        ]
        with patch("pdfplumber.open", return_value=self._mock_pdf([[table]])):
            result = extract_schedules_from_pdf(tmp_path / "test.pdf", 2026)

        assert len(result) == 2
        assert {s.class_type for s in result} == {"CrossFit", "Gymnastics"}

    def test_multiple_days(self, tmp_path):
        table = [
            ["Maandag 14 April", None, None, None],
            ["CrossFit", "w1", "s1", "m1"],
            ["Dinsdag 15 April", None, None, None],
            ["Gymnastics", "w2", "s2", "m2"],
        ]
        with patch("pdfplumber.open", return_value=self._mock_pdf([[table]])):
            result = extract_schedules_from_pdf(tmp_path / "test.pdf", 2026)

        assert result[0].date == date(2026, 4, 14)
        assert result[1].date == date(2026, 4, 15)

    def test_source_file_set(self, tmp_path):
        table = [
            ["Dinsdag 15 April", None, None, None],
            ["CrossFit", None, None, None],
        ]
        pdf_path = tmp_path / "schedule_april.pdf"
        with patch("pdfplumber.open", return_value=self._mock_pdf([[table]])):
            result = extract_schedules_from_pdf(pdf_path, 2026)

        assert result[0].source_file == "schedule_april.pdf"

    def test_class_before_date_ignored(self, tmp_path):
        table = [
            ["CrossFit", "w", "s", "m"],
            ["Maandag 14 April", None, None, None],
            ["Gymnastics", "w2", "s2", "m2"],
        ]
        with patch("pdfplumber.open", return_value=self._mock_pdf([[table]])):
            result = extract_schedules_from_pdf(tmp_path / "test.pdf", 2026)

        assert len(result) == 1
        assert result[0].class_type == "Gymnastics"
