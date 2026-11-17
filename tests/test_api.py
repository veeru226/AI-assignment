from datetime import timedelta

from tests.conftest import ADMIN, make_key

URL = "https://example.com/some/long/path?x=1"


def create(client, auth, **body):
    body.setdefault("url", URL)
    return client.post("/api/v1/links", json=body, headers=auth)


# ---- auth / keys ---------------------------------------------------------
def test_requires_api_key(client):
    r = client.post("/api/v1/links", json={"url": URL})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    r = client.post("/api/v1/links", json={"url": URL}, headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_key_issuing_needs_admin(client):
    assert client.post("/api/v1/keys", json={"name": "x"}).status_code == 401
    assert client.post("/api/v1/keys", json={"name": "x"}, headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.post("/api/v1/keys", json={"name": "x"}, headers={"X-Admin-Key": ADMIN}).status_code == 201


def test_admin_disabled_when_unconfigured(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(env="test", database_url=f"sqlite:///{tmp_path / 'a.db'}", admin_api_key=""))
    with TestClient(app) as c:
        assert c.post("/api/v1/keys", json={"name": "x"}, headers={"X-Admin-Key": "anything"}).status_code == 403


def test_api_key_is_stored_hashed(client, app):
    from sqlalchemy import select

    from app.models import ApiKey

    r = client.post("/api/v1/keys", json={"name": "k"}, headers={"X-Admin-Key": ADMIN})
    raw = r.json()["api_key"]
    with app.state.session_factory() as s:
        stored = s.scalars(select(ApiKey)).all()
    assert all(raw not in (k.key_hash, k.prefix) for k in stored)


# ---- create --------------------------------------------------------------
def test_create_returns_short_link(client, auth):
    r = create(client, auth)
    assert r.status_code == 201
    body = r.json()
    assert len(body["short_code"]) == 7
    assert body["short_url"] == f"https://sho.rt/{body['short_code']}"
    assert body["long_url"] == URL and body["status"] == "active" and body["click_count"] == 0
    assert r.headers["location"] == body["short_url"]


def test_create_is_idempotent_for_same_url(client, auth):
    a, b = create(client, auth), create(client, auth)
    assert (a.status_code, b.status_code) == (201, 200)
    assert a.json()["short_code"] == b.json()["short_code"]


def test_idempotency_normalizes_url_and_is_per_owner(client, auth):
    a = create(client, auth, url="HTTPS://Example.com:443/p")
    b = create(client, auth, url="https://example.com/p")
    assert a.json()["short_code"] == b.json()["short_code"]
    other = make_key(client, "other")
    c = create(client, other, url="https://example.com/p")
    assert c.status_code == 201 and c.json()["short_code"] != a.json()["short_code"]


def test_ttl_requests_are_not_deduplicated(client, auth):
    a = create(client, auth, ttl_seconds=60)
    b = create(client, auth, ttl_seconds=60)
    assert a.json()["short_code"] != b.json()["short_code"]


def test_custom_alias_and_conflict(client, auth):
    r = create(client, auth, custom_alias="my-promo")
    assert r.status_code == 201 and r.json()["short_code"] == "my-promo" and r.json()["is_custom"]
    dup = create(client, auth, url="https://other.example.com/", custom_alias="my-promo")
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "conflict"
    assert client.get("/my-promo").headers["location"] == URL


def test_invalid_inputs(client, auth):
    assert create(client, auth, url="ftp://x.com").status_code == 422
    assert create(client, auth, url="http://localhost/").json()["error"]["code"] == "invalid_url"
    assert create(client, auth, custom_alias="api").status_code == 422
    assert create(client, auth, ttl_seconds=0).status_code == 422
    assert create(client, auth, ttl_seconds=10, expires_at="2099-01-01T00:00:00Z").status_code == 422
    assert create(client, auth, expires_at="2099-01-01T00:00:00").status_code == 422  # naive datetime
    assert create(client, auth, unknown_field=1).status_code == 422
    assert create(client, auth, ttl_seconds=10**10).status_code == 400
    assert client.post("/api/v1/links", json={}, headers=auth).json()["error"]["code"] == "validation_error"


def test_expires_at_must_be_future(client, auth, freeze_time):
    r = create(client, auth, expires_at="2020-01-01T00:00:00Z")
    assert r.status_code == 400


# ---- read / update / delete ---------------------------------------------
def test_get_list_and_owner_isolation(client, auth):
    codes = [create(client, auth, url=f"https://example.com/{i}").json()["short_code"] for i in range(3)]
    assert client.get(f"/api/v1/links/{codes[0]}", headers=auth).status_code == 200
    page = client.get("/api/v1/links?limit=2&offset=0", headers=auth).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["items"][0]["short_code"] == codes[2]
    other = make_key(client, "other")
    assert client.get(f"/api/v1/links/{codes[0]}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/links/{codes[0]}", headers=other).status_code == 404
    assert client.get("/api/v1/links", headers=other).json()["total"] == 0


def test_disable_enable_invalidates_cache(client, auth):
    code = create(client, auth).json()["short_code"]
    assert client.get(f"/{code}").status_code == 302  # warms cache
    r = client.patch(f"/api/v1/links/{code}", json={"is_active": False}, headers=auth)
    assert r.json()["status"] == "disabled"
    assert client.get(f"/{code}").status_code == 410
    client.patch(f"/api/v1/links/{code}", json={"is_active": True}, headers=auth)
    assert client.get(f"/{code}").status_code == 302


def test_patch_expiry_set_and_clear(client, auth, freeze_time):
    code = create(client, auth).json()["short_code"]
    r = client.patch(f"/api/v1/links/{code}", json={"ttl_seconds": 30}, headers=auth)
    assert r.json()["expires_at"] is not None
    r = client.patch(f"/api/v1/links/{code}", json={"expires_at": None}, headers=auth)
    assert r.json()["expires_at"] is None
    assert client.patch(f"/api/v1/links/{code}", json={}, headers=auth).status_code == 422


def test_delete_is_soft_and_frees_nothing(client, auth):
    code = create(client, auth).json()["short_code"]
    client.get(f"/{code}")
    assert client.delete(f"/api/v1/links/{code}", headers=auth).status_code == 204
    assert client.get(f"/{code}").status_code == 410
    assert client.get(f"/api/v1/links/{code}", headers=auth).status_code == 404
    assert client.get("/api/v1/links", headers=auth).json()["total"] == 0
    # an alias can't be re-registered by someone else after deletion (history retained)
    assert create(client, auth, url="https://x.example.com/", custom_alias="reuse-me").status_code == 201
    client.delete("/api/v1/links/reuse-me", headers=auth)
    assert create(client, auth, url="https://y.example.com/", custom_alias="reuse-me").status_code == 409


# ---- bulk ----------------------------------------------------------------
def test_bulk_partial_success(client, auth):
    items = [
        {"url": "https://example.com/1"},
        {"url": "https://example.com/1"},  # same URL -> existing
        {"url": "ftp://bad"},
        {"url": "https://example.com/2", "custom_alias": "bulk-two"},
        {"url": "https://example.com/3", "custom_alias": "bulk-two"},  # conflict
    ]
    r = client.post("/api/v1/links/bulk", json={"items": items}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert [x["status"] for x in body["results"]] == ["created", "existing", "error", "created", "error"]
    assert (body["created"], body["existing"], body["failed"]) == (2, 1, 2)
    assert body["results"][2]["error"]["code"] == "invalid_url"
    assert body["results"][4]["error"]["code"] == "conflict"


def test_bulk_limits(client, auth, settings):
    too_many = [{"url": f"https://example.com/{i}"} for i in range(settings.bulk_max_items + 1)]
    assert client.post("/api/v1/links/bulk", json={"items": too_many}, headers=auth).status_code == 422
    assert client.post("/api/v1/links/bulk", json={"items": []}, headers=auth).status_code == 422


# ---- rate limiting -------------------------------------------------------
def test_rate_limit_per_key(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    s = Settings(env="test", database_url=f"sqlite:///{tmp_path / 'r.db'}", admin_api_key=ADMIN,
                 rate_limit_per_minute=60, rate_limit_burst=3)
    with TestClient(create_app(s)) as c:
        a, b = make_key(c, "a"), make_key(c, "b")
        statuses = [c.get("/api/v1/links", headers=a).status_code for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]
        limited = c.get("/api/v1/links", headers=a)
        assert limited.json()["error"]["code"] == "rate_limited" and int(limited.headers["retry-after"]) >= 1
        assert c.get("/api/v1/links", headers=b).status_code == 200  # other key unaffected


def test_failed_auth_is_throttled_by_ip(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    s = Settings(env="test", database_url=f"sqlite:///{tmp_path / 'f.db'}", rate_limit_per_minute=60, rate_limit_burst=2)
    with TestClient(create_app(s)) as c:
        codes = [c.get("/api/v1/links", headers={"X-API-Key": f"guess{i}"}).status_code for i in range(4)]
        assert codes == [401, 401, 429, 429]


# ---- ops / docs ----------------------------------------------------------
def test_health_ready_and_openapi(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz").json()
    assert ready["status"] == "ready" and "cache" in ready
    spec = client.get("/openapi.json").json()
    assert "/api/v1/links" in spec["paths"] and "/{code}" in spec["paths"]
