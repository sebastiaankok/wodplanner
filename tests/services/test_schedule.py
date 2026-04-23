from datetime import date

from wodplanner.models.schedule import Schedule
from wodplanner.services.schedule import (
    ScheduleService,
    get_all_class_aliases,
    normalize_class_name,
)


class TestNormalizeClassName:
    def test_known_name_unchanged(self):
        assert normalize_class_name("CrossFit") == "CrossFit"

    def test_whitespace_collapsed(self):
        assert normalize_class_name("CrossFit  101") == "CrossFit 101"

    def test_unknown_passthrough(self):
        assert normalize_class_name("SomeUnknownClass") == "SomeUnknownClass"

    def test_strips_leading_trailing(self):
        assert normalize_class_name("  CrossFit  ") == "CrossFit"

    def test_oly_normalizes_to_olympic_lifting(self):
        assert normalize_class_name("Oly") == "Olympic Lifting"

    def test_hycross_canonical(self):
        assert normalize_class_name("HyCross") == "HyCross"


class TestGetAllClassAliases:
    def test_crossfit_includes_itself(self):
        assert "CrossFit" in get_all_class_aliases("CrossFit")

    def test_oly_includes_olympic_lifting(self):
        aliases = get_all_class_aliases("Oly")
        assert "Olympic Lifting" in aliases
        assert "Oly" in aliases

    def test_olympic_lifting_includes_oly(self):
        aliases = get_all_class_aliases("Olympic Lifting")
        assert "Oly" in aliases

    def test_unknown_returns_itself(self):
        assert get_all_class_aliases("Unknown") == ["Unknown"]

    def test_hyrox_resolves_to_hycross(self):
        aliases = get_all_class_aliases("Hyrox")
        assert "HyCross" in aliases


class TestScheduleService:
    def test_add_and_retrieve(self, db_path):
        svc = ScheduleService(db_path)
        s = Schedule(date=date(2026, 1, 5), class_type="CrossFit", metcon="21-15-9", gym_id=1)
        saved = svc.add(s)
        assert saved.id is not None

        fetched = svc.get_by_date_and_class(date(2026, 1, 5), "CrossFit", gym_id=1)
        assert fetched is not None
        assert fetched.metcon == "21-15-9"

    def test_upsert_updates_existing(self, db_path):
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 6), class_type="CrossFit", metcon="first", gym_id=1))
        svc.add(Schedule(date=date(2026, 1, 6), class_type="CrossFit", metcon="updated", gym_id=1))

        fetched = svc.get_by_date_and_class(date(2026, 1, 6), "CrossFit", gym_id=1)
        assert fetched.metcon == "updated"

    def test_bulk_add_returns_count(self, db_path):
        svc = ScheduleService(db_path)
        count = svc.bulk_add([
            Schedule(date=date(2026, 1, 7), class_type="CrossFit", gym_id=1),
            Schedule(date=date(2026, 1, 7), class_type="Gymnastics", gym_id=1),
        ])
        assert count == 2

    def test_get_by_date_returns_all(self, db_path):
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 8), class_type="CrossFit", gym_id=1))
        svc.add(Schedule(date=date(2026, 1, 8), class_type="Gymnastics", gym_id=1))

        results = svc.get_by_date(date(2026, 1, 8), gym_id=1)
        assert len(results) == 2

    def test_alias_lookup(self, db_path):
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 9), class_type="Oly", gym_id=1))

        fetched = svc.get_by_date_and_class(date(2026, 1, 9), "Olympic Lifting", gym_id=1)
        assert fetched is not None

    def test_delete_by_date(self, db_path):
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 10), class_type="CrossFit", gym_id=1))
        deleted = svc.delete_by_date(date(2026, 1, 10))
        assert deleted == 1
        assert svc.get_by_date(date(2026, 1, 10)) == []

    def test_missing_returns_none(self, db_path):
        svc = ScheduleService(db_path)
        assert svc.get_by_date_and_class(date(2099, 1, 1), "CrossFit") is None

    def test_get_all_for_date_alias_map(self, db_path):
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 11), class_type="Oly", gym_id=1))
        mapping = svc.get_all_for_date(date(2026, 1, 11), gym_id=1)
        assert "Olympic Lifting" in mapping
        assert "Oly" in mapping

    def test_gym_id_isolation(self, db_path):
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 12), class_type="CrossFit", metcon="gym1", gym_id=1))
        svc.add(Schedule(date=date(2026, 1, 12), class_type="CrossFit", metcon="gym2", gym_id=2))

        g1 = svc.get_by_date_and_class(date(2026, 1, 12), "CrossFit", gym_id=1)
        g2 = svc.get_by_date_and_class(date(2026, 1, 12), "CrossFit", gym_id=2)
        assert g1.metcon == "gym1"
        assert g2.metcon == "gym2"

    def test_get_all_returns_all_entries(self, db_path):
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 2, 1), class_type="CrossFit", gym_id=1))
        svc.add(Schedule(date=date(2026, 2, 2), class_type="Gymnastics", gym_id=1))
        assert len(svc.get_all()) == 2
