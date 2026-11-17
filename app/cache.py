"""Redirect cache. `Cache` is the seam for a shared backend (e.g. Redis); the
in-memory LRU below is per-process, so with N instances an entry may stay stale
for up to `ttl` seconds after a disable/delete handled by another instance."""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CachedLink:
    link_id: int
    long_url: str
    expires_at: datetime | None


class Cache(Protocol):
    def get(self, key: str) -> CachedLink | None: ...
    def set(self, key: str, value: CachedLink) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...


class LRUCache:
    def __init__(self, max_entries: int, ttl_seconds: float, monotonic=time.monotonic):
        self._max = max_entries
        self._ttl = ttl_seconds
        self._mono = monotonic
        self._data: OrderedDict[str, tuple[float, CachedLink]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> CachedLink | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            stored_at, value = item
            if self._mono() - stored_at > self._ttl:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: CachedLink) -> None:
        with self._lock:
            self._data[key] = (self._mono(), value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
