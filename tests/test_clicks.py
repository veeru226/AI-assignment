import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.clicks import ClickEvent, ClickRecorder
from app.db import Base, make_engine, make_session_factory
from app.geo import NullGeoResolver
from app.models import ApiKey, Click, Link


def _setup(tmp_path, **kw):
    engine = make_engine(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(engine)
    sf = make_session_factory(engine)
    now = datetime.now(timezone.utc)
    with sf() as s:
        s.add(ApiKey(id=1, name="k", prefix="p", key_hash="h", created_at=now))
        s.add(Link(id=1, short_code="abc", long_url="https://e.com/", url_hash="x", api_key_id=1, created_at=now))
        s.commit()
    return sf, ClickRecorder(sf, NullGeoResolver(), "secret", flush_interval=0.02, **kw)


def ev():
    return ClickEvent(1, datetime.now(timezone.utc), "1.2.3.4", "UA", None)


def test_batches_events_and_updates_counter(tmp_path):
    sf, rec = _setup(tmp_path, batch_size=10)
    rec.start()
    for _ in range(25):
        rec.record(ev())
    rec.flush()
    rec.stop()
    with sf() as s:
        assert s.scalar(select(func.count()).select_from(Click)) == 25
        assert s.get(Link, 1).click_count == 25
    assert rec.recorded == 25 and rec.dropped == 0


def test_full_queue_drops_instead_of_blocking(tmp_path):
    _, rec = _setup(tmp_path, queue_size=2)  # worker not started -> queue fills
    start = time.perf_counter()
    for _ in range(5):
        rec.record(ev())
    assert time.perf_counter() - start < 0.5
    assert rec.dropped == 3


def test_stop_drains_pending_events(tmp_path):
    sf, rec = _setup(tmp_path)
    rec.start()
    for _ in range(7):
        rec.record(ev())
    rec.stop()
    with sf() as s:
        assert s.scalar(select(func.count()).select_from(Click)) == 7


def test_visitor_hash_is_not_the_raw_ip(tmp_path):
    sf, rec = _setup(tmp_path)
    rec.start()
    rec.record(ev())
    rec.flush()
    rec.stop()
    with sf() as s:
        h = s.scalars(select(Click.visitor_hash)).first()
    assert "1.2.3.4" not in h and len(h) == 32
