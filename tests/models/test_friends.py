"""Tests for models/friends.py"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from wodplanner.models.friends import Friend


class TestFriend:
    def test_required_fields(self):
        friend = Friend(owner_user_id=1, appuser_id=2, name="John Doe")
        assert friend.owner_user_id == 1
        assert friend.appuser_id == 2
        assert friend.name == "John Doe"

    def test_optional_id_default(self):
        friend = Friend(owner_user_id=1, appuser_id=2, name="John Doe")
        assert friend.id is None

    def test_optional_added_at_default(self):
        friend = Friend(owner_user_id=1, appuser_id=2, name="John Doe")
        assert friend.added_at is None

    def test_all_fields(self):
        now = datetime(2026, 1, 1, 12, 0)
        friend = Friend(id=1, owner_user_id=1, appuser_id=2, name="John Doe", added_at=now)
        assert friend.id == 1
        assert friend.added_at == now

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Friend(owner_user_id=1, name="John Doe")  # missing appuser_id
