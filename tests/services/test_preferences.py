
from wodplanner.services.preferences import PreferencesService


class TestPreferencesService:
    def test_get_hidden_class_types_empty_by_default(self, db_path):
        svc = PreferencesService(db_path)
        assert svc.get_hidden_class_types(user_id=1) == []

    def test_set_hidden_class_types(self, db_path):
        svc = PreferencesService(db_path)
        svc.set_hidden_class_types(user_id=1, types=["CrossFit", "Olympic Lifting"])
        assert svc.get_hidden_class_types(user_id=1) == ["CrossFit", "Olympic Lifting"]

    def test_toggle_hidden_class_type_add(self, db_path):
        svc = PreferencesService(db_path)
        result = svc.toggle_hidden_class_type(user_id=1, class_type="CrossFit")
        assert "CrossFit" in result
        assert svc.get_hidden_class_types(user_id=1) == ["CrossFit"]

    def test_toggle_hidden_class_type_remove(self, db_path):
        svc = PreferencesService(db_path)
        svc.set_hidden_class_types(user_id=1, types=["CrossFit", "Gymnastics"])
        result = svc.toggle_hidden_class_type(user_id=1, class_type="CrossFit")
        assert "CrossFit" not in result
        assert result == ["Gymnastics"]

    def test_toggle_hidden_class_type_empty_to_non_empty(self, db_path):
        svc = PreferencesService(db_path)
        svc.toggle_hidden_class_type(user_id=1, class_type="Oly")
        svc.toggle_hidden_class_type(user_id=1, class_type="CrossFit")
        assert svc.get_hidden_class_types(user_id=1) == ["Oly", "CrossFit"]

    def test_get_dismissed_tooltips_empty_by_default(self, db_path):
        svc = PreferencesService(db_path)
        assert svc.get_dismissed_tooltips(user_id=1) == []

    def test_dismiss_tooltip_adds(self, db_path):
        svc = PreferencesService(db_path)
        svc.dismiss_tooltip(user_id=1, tooltip_id="welcome_banner")
        assert "welcome_banner" in svc.get_dismissed_tooltips(user_id=1)

    def test_dismiss_tooltip_no_duplicates(self, db_path):
        svc = PreferencesService(db_path)
        svc.dismiss_tooltip(user_id=1, tooltip_id="welcome_banner")
        svc.dismiss_tooltip(user_id=1, tooltip_id="welcome_banner")
        assert svc.get_dismissed_tooltips(user_id=1).count("welcome_banner") == 1

    def test_get_all_returns_complete_preferences(self, db_path):
        svc = PreferencesService(db_path)
        svc.set_hidden_class_types(user_id=1, types=["CrossFit"])
        svc.dismiss_tooltip(user_id=1, tooltip_id="tip1")
        prefs = svc.get_all(user_id=1)
        assert prefs.hidden_class_types == ["CrossFit"]

    def test_user_isolation(self, db_path):
        svc = PreferencesService(db_path)
        svc.set_hidden_class_types(user_id=1, types=["CrossFit"])
        svc.set_hidden_class_types(user_id=2, types=["Gymnastics"])
        assert svc.get_hidden_class_types(user_id=1) == ["CrossFit"]
        assert svc.get_hidden_class_types(user_id=2) == ["Gymnastics"]

    def test_migration_from_old_schema(self, tmp_path, clean_registry):
        import sqlite3

        from wodplanner.services import migrations

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO preferences VALUES ('hidden_class_types', '[\"OldClass\"]')")
        conn.commit()
        conn.close()

        migrations._reset_for_tests()
        migrations.ensure_migrations(db_path)

        conn2 = sqlite3.connect(db_path)
        row = conn2.execute("SELECT value FROM preferences WHERE user_id = 0 AND key = 'hidden_class_types'").fetchone()
        conn2.close()
        assert row is not None
        assert "OldClass" in row[0]