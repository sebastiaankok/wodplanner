"""In-memory rate limiter for failed login attempts per IP."""

import logging
import time

logger = logging.getLogger(__name__)

# Delay in seconds after N consecutive failures (index = fail count - 1, capped at last)
_DELAYS = [5, 15, 60, 300, 900]


class LoginRateLimiter:
    def __init__(self) -> None:
        self._state: dict[str, tuple[int, float]] = {}  # ip -> (fail_count, unblock_at)

    def is_blocked(self, ip: str) -> tuple[bool, float]:
        """Return (blocked, seconds_remaining)."""
        entry = self._state.get(ip)
        if entry is None:
            return False, 0.0
        _, unblock_at = entry
        remaining = unblock_at - time.monotonic()
        return remaining > 0, max(remaining, 0.0)

    def record_failure(self, ip: str) -> None:
        entry = self._state.get(ip)
        fail_count = (entry[0] if entry else 0) + 1
        delay = _DELAYS[min(fail_count - 1, len(_DELAYS) - 1)]
        unblock_at = time.monotonic() + delay
        self._state[ip] = (fail_count, unblock_at)
        logger.warning("Login failed for %s (attempt %d, blocked %ds)", ip, fail_count, delay)

    def record_success(self, ip: str) -> None:
        self._state.pop(ip, None)


limiter = LoginRateLimiter()
