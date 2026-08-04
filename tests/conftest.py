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
def make_user(db_path):
    """Create users in the `users` table (FK parents for user-scoped inserts)."""
    from wodplanner.services.users import UserService

    svc = UserService(db_path)

    def _make(*user_ids: int):
        for uid in user_ids:
            svc.upsert(user_id=uid, appuser_id=None, gym_id=uid, display_name=str(uid))
        return svc

    return _make


@pytest.fixture
def clean_registry():
    """Save and restore the migration registry so test-only registrations don't leak."""
    original = list(migrations._registry)
    yield
    migrations._registry[:] = original
    migrations._reset_for_tests()
