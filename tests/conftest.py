import pytest

from wodplanner.services import migrations


@pytest.fixture
def db_path(tmp_path):
    """Temp SQLite DB with all migrations applied. Fresh path per test avoids cache collisions."""
    migrations._reset_for_tests()
    path = tmp_path / "test.db"
    migrations.ensure_migrations(path)
    return path


@pytest.fixture
def clean_registry():
    """Save and restore the migration registry so test-only registrations don't leak."""
    original = list(migrations._registry)
    yield
    migrations._registry[:] = original
    migrations._reset_for_tests()
