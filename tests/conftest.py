import pytest
from fastapi.testclient import TestClient

from app import clock
from app.config import Settings
from app.main import create_app

ADMIN = "test-admin-key"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        base_url="https://sho.rt",
        secret_key="test-secret",
        admin_api_key=ADMIN,
        rate_limit_per_minute=600,
        rate_limit_burst=1000,
        click_flush_interval=0.05,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    # follow_redirects=False so tests can assert on the 302 itself
    with TestClient(app, follow_redirects=False, base_url="https://sho.rt") as c:
        yield c


def make_key(client, name="tester") -> dict:
    r = client.post("/api/v1/keys", json={"name": name}, headers={"X-Admin-Key": ADMIN})
    assert r.status_code == 201, r.text
    return {"X-API-Key": r.json()["api_key"]}


@pytest.fixture
def auth(client):
    return make_key(client)


@pytest.fixture
def freeze_time(monkeypatch):
    """Returns a function to set/advance the service clock."""
    from datetime import datetime, timezone

    state = {"now": datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    def set_now(value):
        state["now"] = value
        return value

    return set_now
