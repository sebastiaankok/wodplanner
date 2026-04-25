"""Tests for app/routers/friends.py."""


class TestFriendsRouter:
    def test_list_unauthenticated(self, app_client):
        assert app_client.get("/api/friends").status_code == 401

    def test_add_and_list(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/api/friends", json={"appuser_id": 555, "name": "Alice"}
        )
        assert response.status_code == 200
        added = response.json()
        assert added["appuser_id"] == 555
        assert added["name"] == "Alice"

        listed = app_client.get("/api/friends").json()
        assert len(listed) == 1
        assert listed[0]["appuser_id"] == 555

    def test_get_friend_200(self, app_client, session_cookie, friends_service):
        friend = friends_service.add(owner_user_id=42, appuser_id=10, name="Bob")
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(f"/api/friends/{friend.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Bob"

    def test_get_friend_404(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/api/friends/9999")
        assert response.status_code == 404

    def test_delete_friend_200(self, app_client, session_cookie, friends_service):
        friend = friends_service.add(owner_user_id=42, appuser_id=20, name="Carol")
        app_client.cookies.set("session", session_cookie)
        response = app_client.delete(f"/api/friends/{friend.id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_friend_404(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.delete("/api/friends/9999")
        assert response.status_code == 404
