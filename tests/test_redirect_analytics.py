from datetime import datetime, timedelta, timezone

from tests.conftest import make_key

URL = "https://example.com/landing"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def new_link(client, auth, **body):
    """Create a link (default URL) via the API and return its short code."""
    body.setdefault("url", URL)
    return client.post("/api/v1/links", json=body, headers=auth).json()["short_code"]


def click(client, code, ua=CHROME, referer=None, **headers):
    """GET a short code with the given User-Agent, optional Referer, and extra headers."""
    h = {"User-Agent": ua, **headers}
    if referer:
        h["Referer"] = referer
    return client.get(f"/{code}", headers=h)


def flush(app):
    """Flush the app's click recorder so queued clicks are persisted."""
    app.state.recorder.flush()


# ---- redirect ------------------------------------------------------------
def test_redirect_302_to_destination(client, auth):
    """A short code redirects with 302 to the original URL."""
    code = new_link(client, auth)
    r = click(client, code)
    assert r.status_code == 302 and r.headers["location"] == URL


def test_unknown_and_malformed_codes_404(client):
    """Unknown or malformed codes return 404 with a not_found error."""
    assert client.get("/nope123").status_code == 404
    assert client.get("/a").status_code == 404
    assert client.get("/nope123").json()["error"]["code"] == "not_found"


def test_expired_link_returns_410_even_when_cached(client, auth, freeze_time):
    """A link past its TTL returns 410 gone even if it was cached, and reports status expired."""
    code = new_link(client, auth, ttl_seconds=60)
    assert click(client, code).status_code == 302  # cached now
    freeze_time(datetime(2030, 1, 1, 12, 1, 1, tzinfo=timezone.utc))
    r = click(client, code)
    assert r.status_code == 410 and r.json()["error"]["code"] == "gone"
    assert client.get(f"/api/v1/links/{code}", headers=auth).json()["status"] == "expired"


def test_cache_serves_repeat_redirects_without_db_lookup(client, auth, app):
    """A repeated redirect is served from the cache (cache hit count increases by one)."""
    code = new_link(client, auth)
    click(client, code)
    hits = app.state.cache.hits
    click(client, code)
    assert app.state.cache.hits == hits + 1


def test_head_requests_are_not_counted(client, auth, app):
    """HEAD requests redirect but do not increment the click count."""
    code = new_link(client, auth)
    assert client.head(f"/{code}").status_code == 302
    flush(app)
    assert client.get(f"/api/v1/links/{code}", headers=auth).json()["click_count"] == 0


def test_reserved_routes_not_shadowed(client):
    """Reserved routes such as /docs and /healthz are not captured by the short-code route."""
    assert client.get("/docs").status_code == 200
    assert client.get("/healthz").status_code == 200


# ---- analytics -----------------------------------------------------------
def test_click_count_and_last_clicked(client, auth, app):
    """Clicks update the link's click_count and last_clicked_at."""
    code = new_link(client, auth)
    for _ in range(5):
        click(client, code)
    flush(app)
    link = client.get(f"/api/v1/links/{code}", headers=auth).json()
    assert link["click_count"] == 5 and link["last_clicked_at"]


def test_stats_breakdowns(client, auth, app):
    """Stats report totals, referrers, browsers, OSes, devices, unique visitors, and timeseries."""
    code = new_link(client, auth)
    click(client, code, ua=CHROME, referer="https://news.example.org/story?id=1")
    click(client, code, ua=CHROME, referer="https://news.example.org/other")
    click(client, code, ua=IPHONE)  # direct, mobile
    flush(app)
    s = client.get(f"/api/v1/links/{code}/stats", headers=auth).json()
    assert s["total_clicks"] == s["clicks_in_range"] == 3
    assert s["referrers"][0] == {"value": "news.example.org", "clicks": 2}
    assert {"value": "direct", "clicks": 1} in s["referrers"]
    assert s["browsers"][0] == {"value": "Chrome", "clicks": 2}
    assert {"value": "Windows", "clicks": 2} in s["operating_systems"]
    assert {"value": "iOS", "clicks": 1} in s["operating_systems"]
    assert {c["value"] for c in s["devices"]} == {"Desktop", "Mobile"}
    # TestClient always connects from the same address -> one unique visitor
    assert s["unique_visitors_in_range"] == 1
    assert sum(b["clicks"] for b in s["timeseries"]) == 3


def test_unique_visitors_use_forwarded_ip_when_trusted(tmp_path):
    """With trusted proxy headers, X-Forwarded-For sets unique visitors and CF-IPCountry sets country."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from tests.conftest import ADMIN

    s = Settings(env="test", database_url=f"sqlite:///{tmp_path / 'u.db'}", admin_api_key=ADMIN,
                 trust_proxy_headers=True, click_flush_interval=0.05, rate_limit_burst=1000, rate_limit_per_minute=600)
    app = create_app(s)
    with TestClient(app, follow_redirects=False) as c:
        auth = make_key(c)
        code = new_link(c, auth)
        click(c, code, **{"X-Forwarded-For": "203.0.113.1, 10.0.0.1", "CF-IPCountry": "DE"})
        click(c, code, **{"X-Forwarded-For": "203.0.113.1", "CF-IPCountry": "DE"})
        click(c, code, **{"X-Forwarded-For": "198.51.100.7", "CF-IPCountry": "US"})
        click(c, code, **{"X-Forwarded-For": "198.51.100.8", "CF-IPCountry": "garbage"})
        flush(app)
        st = c.get(f"/api/v1/links/{code}/stats", headers=auth).json()
        assert st["unique_visitors_in_range"] == 3
        assert st["countries"][0] == {"value": "DE", "clicks": 2}
        assert {"value": "unknown", "clicks": 1} in st["countries"]


def test_forwarded_headers_ignored_by_default(client, auth, app):
    """Without trust_proxy_headers, forwarded IP and country headers are ignored."""
    code = new_link(client, auth)
    click(client, code, **{"X-Forwarded-For": "1.1.1.1", "CF-IPCountry": "FR"})
    click(client, code, **{"X-Forwarded-For": "2.2.2.2", "CF-IPCountry": "FR"})
    flush(app)
    s = client.get(f"/api/v1/links/{code}/stats", headers=auth).json()
    assert s["unique_visitors_in_range"] == 1
    assert s["countries"] == [{"value": "unknown", "clicks": 2}]


def test_timeseries_hourly_and_daily_with_zero_fill(client, auth, app, freeze_time):
    """Stats timeseries buckets clicks hourly or daily, zero-filling empty buckets."""
    code = new_link(client, auth)
    for ts in (
        datetime(2030, 1, 1, 12, 5, tzinfo=timezone.utc),
        datetime(2030, 1, 1, 12, 50, tzinfo=timezone.utc),
        datetime(2030, 1, 1, 14, 0, tzinfo=timezone.utc),
        datetime(2030, 1, 3, 9, 0, tzinfo=timezone.utc),
    ):
        freeze_time(ts)
        click(client, code)
    flush(app)

    hourly = client.get(
        f"/api/v1/links/{code}/stats",
        params={"from": "2030-01-01T12:00:00Z", "to": "2030-01-01T15:00:00Z", "granularity": "hour"},
        headers=auth,
    ).json()
    assert [b["clicks"] for b in hourly["timeseries"]] == [2, 0, 1, 0]
    assert hourly["clicks_in_range"] == 3

    daily = client.get(
        f"/api/v1/links/{code}/stats",
        params={"from": "2030-01-01T00:00:00Z", "to": "2030-01-04T00:00:00Z"},
        headers=auth,
    ).json()
    assert [b["clicks"] for b in daily["timeseries"]] == [3, 0, 1, 0]
    assert daily["total_clicks"] == 4


def test_stats_validation_and_isolation(client, auth):
    """Stats reject bad ranges/granularity and are hidden from other owners and unauthenticated calls."""
    code = new_link(client, auth)
    base = f"/api/v1/links/{code}/stats"
    assert client.get(base, params={"from": "2030-02-01T00:00:00Z", "to": "2030-01-01T00:00:00Z"}, headers=auth).status_code == 400
    assert client.get(base, params={"from": "2020-01-01T00:00:00Z", "to": "2030-01-01T00:00:00Z", "granularity": "hour"}, headers=auth).status_code == 400
    assert client.get(base, params={"granularity": "minute"}, headers=auth).status_code == 422
    assert client.get(base, headers=make_key(client, "intruder")).status_code == 404
    assert client.get(base).status_code == 401
    assert client.get("/api/v1/links/missing/stats", headers=auth).status_code == 404


def test_clicks_survive_restart(settings):
    """Persistence: data written by one app instance is visible to a new one."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    first = create_app(settings)
    with TestClient(first, follow_redirects=False) as c:
        auth = make_key(c)
        code = new_link(c, auth)
        click(c, code)
        flush(first)
    second = create_app(settings)
    with TestClient(second, follow_redirects=False) as c:
        assert click(c, code).headers["location"] == URL
