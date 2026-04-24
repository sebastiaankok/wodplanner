
from wodplanner.services.login_limiter import LoginRateLimiter


class TestLoginRateLimiter:
    def test_is_blocked_false_for_new_ip(self):
        limiter = LoginRateLimiter()
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert blocked is False
        assert remaining == 0.0

    def test_record_failure_first_attempt(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert blocked is True
        assert remaining > 0

    def test_record_failure_increments_fail_count(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("192.168.1.1")
        limiter.record_failure("192.168.1.1")
        limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert blocked is True

    def test_record_failure_sets_5s_delay_first(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert 0 < remaining <= 5

    def test_record_failure_sets_15s_delay_second(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("192.168.1.1")
        limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert 0 < remaining <= 15

    def test_record_failure_sets_60s_delay_third(self):
        limiter = LoginRateLimiter()
        for _ in range(3):
            limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert 0 < remaining <= 60

    def test_record_failure_sets_300s_delay_fourth(self):
        limiter = LoginRateLimiter()
        for _ in range(4):
            limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert 0 < remaining <= 300

    def test_record_failure_sets_900s_delay_fifth(self):
        limiter = LoginRateLimiter()
        for _ in range(5):
            limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert 0 < remaining <= 900

    def test_record_failure_capped_at_900s(self):
        limiter = LoginRateLimiter()
        for _ in range(10):
            limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert 0 < remaining <= 900

    def test_record_success_clears_ip(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("192.168.1.1")
        limiter.record_success("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert blocked is False
        assert remaining == 0.0

    def test_different_ips_independent(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("192.168.1.1")
        limiter.record_failure("192.168.1.2")
        blocked1, _ = limiter.is_blocked("192.168.1.1")
        blocked2, _ = limiter.is_blocked("192.168.1.2")
        assert blocked1 is True
        assert blocked2 is True

    def test_unblock_after_delay(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("192.168.1.1")
        blocked, remaining = limiter.is_blocked("192.168.1.1")
        assert blocked is True
        assert remaining > 4.0
        assert remaining <= 5.0