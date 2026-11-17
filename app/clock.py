"""Single time source so tests can control "now" (TTL expiry, analytics buckets)."""
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)
