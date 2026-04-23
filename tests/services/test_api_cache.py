import threading
import time

from wodplanner.services.api_cache import ApiCacheService


class TestApiCacheService:
    def test_get_returns_none_for_missing_key(self):
        cache = ApiCacheService(ttl_seconds=60)
        assert cache.get("nonexistent") is None

    def test_get_returns_value_before_ttl(self):
        cache = ApiCacheService(ttl_seconds=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_returns_none_after_ttl(self):
        cache = ApiCacheService(ttl_seconds=1)
        cache.set("key1", "value1")
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_set_stores_value_with_expiry(self):
        cache = ApiCacheService(ttl_seconds=120)
        cache.set("test_key", {"data": 123})
        result = cache.get("test_key")
        assert result == {"data": 123}

    def test_invalidate_removes_entry(self):
        cache = ApiCacheService(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_invalidate_nonexistent_key_does_not_raise(self):
        cache = ApiCacheService(ttl_seconds=60)
        cache.invalidate("nonexistent")

    def test_multiple_keys_are_independent(self):
        cache = ApiCacheService(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"

    def test_overwrite_key_updates_value(self):
        cache = ApiCacheService(ttl_seconds=60)
        cache.set("key1", "old_value")
        cache.set("key1", "new_value")
        assert cache.get("key1") == "new_value"


class TestApiCacheServiceThreadSafety:
    def test_concurrent_get_set(self):
        cache = ApiCacheService(ttl_seconds=60)
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"key_{i % 10}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    for i in range(10):
                        cache.get(f"key_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_invalidate(self):
        cache = ApiCacheService(ttl_seconds=60)
        for i in range(10):
            cache.set(f"key_{i}", f"value_{i}")

        errors = []

        def invalidator():
            try:
                for _ in range(50):
                    for i in range(10):
                        cache.invalidate(f"key_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=invalidator) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0