"""Asynchronous click recording.

The redirect handler only does a non-blocking `queue.put_nowait`. A single
background thread drains the queue in batches, enriches events (UA parsing,
GeoIP, visitor hashing) and writes them in one transaction, so redirect latency
is independent of database write latency.

Trade-off: the queue is in memory. A hard crash can lose up to one flush
interval of clicks, and a full queue drops events (counted in `dropped`)
rather than slowing redirects. A durable broker (Kafka/SQS/Redis Streams) is
the upgrade path when click loss is unacceptable.
"""
import hmac
import hashlib
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from app.enrich import parse_user_agent, referrer_host
from app.geo import GeoResolver
from app.models import Click, Link

log = logging.getLogger(__name__)
_STOP = object()


@dataclass(frozen=True)
class ClickEvent:
    link_id: int
    clicked_at: datetime
    ip: str | None
    user_agent: str | None
    referrer: str | None
    country_hint: str | None = None


class ClickRecorder:
    def __init__(
        self,
        session_factory: sessionmaker,
        geo: GeoResolver,
        secret: str,
        queue_size: int = 100_000,
        batch_size: int = 500,
        flush_interval: float = 0.5,
    ):
        self._sf = session_factory
        self._geo = geo
        self._secret = secret.encode()
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._batch_size = batch_size
        self._interval = flush_interval
        self._thread: threading.Thread | None = None
        self.dropped = 0
        self.recorded = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="click-recorder", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Drain remaining events, then stop the worker."""
        if self._thread and self._thread.is_alive():
            self._queue.put(_STOP)
            self._thread.join(timeout)

    def record(self, event: ClickEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1

    def flush(self) -> None:
        """Block until everything queued so far is persisted (tests, shutdown hooks)."""
        self._queue.join()

    def _run(self) -> None:
        stopping = False
        while not stopping:
            batch = []
            try:
                item = self._queue.get(timeout=self._interval)
            except queue.Empty:
                continue
            stopping = self._take(item, batch)
            while len(batch) < self._batch_size and not stopping:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                stopping = self._take(item, batch)
            if batch:
                self._persist(batch)
            for _ in range(len(batch) + (1 if stopping else 0)):
                self._queue.task_done()

    @staticmethod
    def _take(item, batch) -> bool:
        if item is _STOP:
            return True
        batch.append(item)
        return False

    def _visitor_hash(self, ip: str | None) -> str:
        return hmac.new(self._secret, (ip or "unknown").encode(), hashlib.sha256).hexdigest()[:32]

    def _persist(self, events: list[ClickEvent]) -> None:
        rows = []
        per_link: dict[int, tuple[int, datetime]] = {}
        for ev in events:
            info = parse_user_agent(ev.user_agent)
            ts = ev.clicked_at.astimezone(timezone.utc)
            rows.append(
                Click(
                    link_id=ev.link_id,
                    clicked_at=ts,
                    hour_bucket=ts.replace(minute=0, second=0, microsecond=0),
                    day_bucket=ts.date(),
                    referrer_host=referrer_host(ev.referrer),
                    browser=info.browser,
                    os=info.os,
                    device=info.device,
                    country=self._geo.country(ev.ip, ev.country_hint),
                    visitor_hash=self._visitor_hash(ev.ip),
                )
            )
            count, last = per_link.get(ev.link_id, (0, ts))
            per_link[ev.link_id] = (count + 1, max(last, ts))
        try:
            with self._sf() as session:
                session.add_all(rows)
                for link_id, (count, last) in per_link.items():
                    session.execute(
                        update(Link)
                        .where(Link.id == link_id)
                        .values(click_count=Link.click_count + count, last_clicked_at=last)
                    )
                session.commit()
            self.recorded += len(rows)
        except Exception:
            log.exception("Failed to persist %d click events", len(rows))
            self.dropped += len(rows)
