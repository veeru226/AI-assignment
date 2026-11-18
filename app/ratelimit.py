"""Token-bucket rate limiter. `RateLimiter` is the seam for a shared backend;
this in-process version limits per instance (effective limit = N x configured)."""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    remaining: int
    retry_after: float  # seconds until one token is available (0 when allowed)


class TokenBucketLimiter:
    def __init__(self, per_minute: int, burst: int, max_keys: int = 100_000, monotonic=time.monotonic):
        """Configure the refill rate, burst capacity, key cap and clock."""
        self._rate = per_minute / 60.0
        self._burst = max(burst, 1)
        self._max_keys = max_keys
        self._mono = monotonic
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()  # key -> (tokens, last)
        self._lock = threading.Lock()

    def check(self, key: str) -> RateDecision:
        """Consume one token for the key and return whether the request is allowed."""
        now = self._mono()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self._burst), now))
            tokens = min(self._burst, tokens + (now - last) * self._rate)
            if tokens >= 1:
                tokens -= 1
                allowed, retry = True, 0.0
            else:
                allowed = False
                retry = (1 - tokens) / self._rate if self._rate > 0 else 60.0
            self._buckets[key] = (tokens, now)
            self._buckets.move_to_end(key)
            while len(self._buckets) > self._max_keys:  # bounds memory under key-spraying
                self._buckets.popitem(last=False)
            return RateDecision(allowed, int(tokens), retry)
