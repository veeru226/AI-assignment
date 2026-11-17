import hashlib
import hmac
import secrets

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import AppError
from app.models import ApiKey

KEY_PREFIX = "usk_"


def hash_key(raw: str) -> str:
    # API keys are 256-bit random values, so a fast unsalted hash is sufficient
    # (unlike passwords, there is nothing to brute-force).
    return hashlib.sha256(raw.encode()).hexdigest()


def create_api_key(session: Session, name: str) -> tuple[ApiKey, str]:
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    record = ApiKey(name=name, prefix=raw[:12], key_hash=hash_key(raw), is_active=True, created_at=clock.now())
    session.add(record)
    session.commit()
    return record, raw


def client_ip(request: Request) -> str | None:
    if request.app.state.settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def _throttle(request: Request, bucket_key: str) -> None:
    decision = request.app.state.limiter.check(bucket_key)
    if not decision.allowed:
        raise AppError(
            429,
            "rate_limited",
            "Too many requests",
            headers={"Retry-After": str(max(1, int(decision.retry_after + 0.999)))},
        )


def get_owner(
    request: Request,
    session: Session = Depends(get_session),
    x_api_key: str | None = Header(default=None, description="API key issued via POST /api/v1/keys"),
) -> ApiKey:
    """Authenticate, then rate-limit per key. Failed auth is rate-limited per IP so key
    guessing is throttled."""
    if not x_api_key:
        _throttle(request, f"ip:{client_ip(request)}")
        raise AppError(401, "unauthorized", "Missing X-API-Key header", {"WWW-Authenticate": "ApiKey"})
    key = session.scalars(select(ApiKey).where(ApiKey.key_hash == hash_key(x_api_key))).first()
    if key is None or not key.is_active:
        _throttle(request, f"ip:{client_ip(request)}")
        raise AppError(401, "unauthorized", "Invalid API key", {"WWW-Authenticate": "ApiKey"})
    _throttle(request, f"key:{key.id}")
    return key


def require_admin(request: Request, x_admin_key: str | None = Header(default=None)) -> None:
    configured = request.app.state.settings.admin_api_key
    if not configured:
        raise AppError(403, "admin_disabled", "Key management is disabled (ADMIN_API_KEY not set)")
    if not x_admin_key or not hmac.compare_digest(x_admin_key.encode(), configured.encode()):
        _throttle(request, f"ip:{client_ip(request)}")
        raise AppError(401, "unauthorized", "Invalid admin key")
