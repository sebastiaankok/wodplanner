from wodplanner.services.friends import FriendsService


class TestFriendsService:
    def test_add_and_get(self, db_path):
        svc = FriendsService(db_path)
        f = svc.add(owner_user_id=1, appuser_id=100, name="Alice")
        assert f.id is not None
        assert f.name == "Alice"

        fetched = svc.get(owner_user_id=1, friend_id=f.id)
        assert fetched is not None
        assert fetched.name == "Alice"

    def test_get_scoped_to_owner(self, db_path):
        svc = FriendsService(db_path)
        f = svc.add(owner_user_id=1, appuser_id=200, name="Bob")
        assert svc.get(owner_user_id=2, friend_id=f.id) is None

    def test_get_by_appuser_id(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=1, appuser_id=300, name="Carol")
        fetched = svc.get_by_appuser_id(owner_user_id=1, appuser_id=300)
        assert fetched is not None
        assert fetched.name == "Carol"

    def test_get_by_appuser_id_wrong_owner(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=1, appuser_id=400, name="Dave")
        assert svc.get_by_appuser_id(owner_user_id=2, appuser_id=400) is None

    def test_get_all_scoped(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=10, appuser_id=1, name="Alice")
        svc.add(owner_user_id=10, appuser_id=2, name="Bob")
        svc.add(owner_user_id=20, appuser_id=3, name="Carol")

        results = svc.get_all(owner_user_id=10)
        assert {f.name for f in results} == {"Alice", "Bob"}

    def test_upsert_updates_name(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=1, appuser_id=500, name="Old Name")
        svc.add(owner_user_id=1, appuser_id=500, name="New Name")
        fetched = svc.get_by_appuser_id(owner_user_id=1, appuser_id=500)
        assert fetched.name == "New Name"

    def test_get_appuser_ids(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=1, appuser_id=601, name="Alice")
        svc.add(owner_user_id=1, appuser_id=602, name="Bob")
        svc.add(owner_user_id=2, appuser_id=603, name="Carol")
        assert svc.get_appuser_ids(owner_user_id=1) == {601, 602}

    def test_delete(self, db_path):
        svc = FriendsService(db_path)
        f = svc.add(owner_user_id=1, appuser_id=700, name="Eve")
        assert svc.delete(owner_user_id=1, friend_id=f.id) is True
        assert svc.get(owner_user_id=1, friend_id=f.id) is None

    def test_delete_wrong_owner_returns_false(self, db_path):
        svc = FriendsService(db_path)
        f = svc.add(owner_user_id=1, appuser_id=800, name="Frank")
        assert svc.delete(owner_user_id=2, friend_id=f.id) is False

    def test_delete_by_appuser_id(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=1, appuser_id=900, name="Grace")
        assert svc.delete_by_appuser_id(owner_user_id=1, appuser_id=900) is True
        assert svc.get_by_appuser_id(owner_user_id=1, appuser_id=900) is None

    def test_delete_by_appuser_id_wrong_owner(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=1, appuser_id=1000, name="Heidi")
        assert svc.delete_by_appuser_id(owner_user_id=2, appuser_id=1000) is False

    def test_cross_user_isolation_get_all(self, db_path):
        svc = FriendsService(db_path)
        svc.add(owner_user_id=1, appuser_id=50, name="User50")
        assert svc.get_all(owner_user_id=99) == []
