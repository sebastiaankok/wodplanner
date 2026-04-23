import pytest

from wodplanner.services import migrations
from wodplanner.services.db import get_connection


def test_register_duplicate_same_fn_is_noop(clean_registry):
    def my_fn(conn):
        pass

    migrations.register(9999, "test migration", my_fn)
    migrations.register(9999, "test migration", my_fn)  # must not raise
    assert sum(1 for e in migrations._registry if e.version == 9999) == 1


def test_register_duplicate_different_version_raises(clean_registry):
    def fn1(conn):
        pass

    def fn2(conn):
        pass

    migrations.register(9998, "first", fn1)
    with pytest.raises(ValueError, match="9998"):
        migrations.register(9998, "second", fn2)


def test_run_all_applies_migrations(tmp_path):
    migrations._reset_for_tests()
    path = tmp_path / "mig_test.db"
    with get_connection(path) as conn:
        ran = migrations.run_all(conn)

    assert 100 in ran  # schedule
    assert 200 in ran  # friends


def test_run_all_idempotent(tmp_path):
    migrations._reset_for_tests()
    path = tmp_path / "mig_idem.db"
    with get_connection(path) as conn:
        ran1 = migrations.run_all(conn)
        ran2 = migrations.run_all(conn)

    assert len(ran1) > 0
    assert ran2 == []


def test_ensure_migrations_skips_second_call(tmp_path):
    migrations._reset_for_tests()
    path = tmp_path / "mig_once.db"
    ran1 = migrations.ensure_migrations(path)
    ran2 = migrations.ensure_migrations(path)

    assert len(ran1) > 0
    assert ran2 == []


def test_schema_migrations_table_records_versions(tmp_path):
    migrations._reset_for_tests()
    path = tmp_path / "mig_record.db"
    migrations.ensure_migrations(path)
    with get_connection(path) as conn:
        versions = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    assert 100 in versions
    assert 200 in versions
