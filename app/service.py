import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import clock
from app.cache import Cache, CachedLink
from app.codegen import CodeGenerator
from app.config import Settings
from app.errors import AppError, bad_request, conflict, not_found
from app.models import Link
from app.schemas import CreateLinkRequest, LinkOut, UpdateLinkRequest
from app.urlutil import normalize_url, url_hash, validate_alias


def link_status(link: Link, now: datetime) -> str:
    if link.deleted_at is not None or not link.is_active:
        return "disabled"
    if link.expires_at is not None and link.expires_at <= now:
        return "expired"
    return "active"


class LinkService:
    def __init__(self, settings: Settings, codegen: CodeGenerator, cache: Cache):
        self.settings = settings
        self.codegen = codegen
        self.cache = cache
        self._own_host = (urlsplit(settings.base_url).hostname or "").lower() or None

    # ---- presentation -------------------------------------------------
    def to_out(self, link: Link) -> LinkOut:
        return LinkOut(
            short_code=link.short_code,
            short_url=f"{self.settings.base_url.rstrip('/')}/{link.short_code}",
            long_url=link.long_url,
            is_custom=link.is_custom,
            is_active=link.is_active,
            status=link_status(link, clock.now()),  # type: ignore[arg-type]
            created_at=link.created_at,
            expires_at=link.expires_at,
            click_count=link.click_count,
            last_clicked_at=link.last_clicked_at,
        )

    # ---- helpers ------------------------------------------------------
    def _resolve_expiry(self, ttl_seconds: int | None, expires_at: datetime | None, now: datetime) -> datetime | None:
        if ttl_seconds is not None:
            if ttl_seconds > self.settings.max_ttl_seconds:
                raise bad_request(f"ttl_seconds must be <= {self.settings.max_ttl_seconds}")
            return now + timedelta(seconds=ttl_seconds)
        if expires_at is not None:
            if expires_at <= now:
                raise bad_request("expires_at must be in the future")
            if expires_at - now > timedelta(seconds=self.settings.max_ttl_seconds):
                raise bad_request("expires_at is too far in the future")
        return expires_at

    # ---- create -------------------------------------------------------
    def create(self, session: Session, owner_id: int, req: CreateLinkRequest) -> tuple[Link, bool]:
        """Returns (link, created). Same owner + same URL (no alias/expiry) is idempotent."""
        now = clock.now()
        long_url = normalize_url(
            req.url,
            max_length=self.settings.max_url_length,
            allow_private=self.settings.allow_private_targets,
            own_host=self._own_host,
        )
        digest = url_hash(long_url)
        expires_at = self._resolve_expiry(req.ttl_seconds, req.expires_at, now)

        if req.custom_alias is None and expires_at is None:
            existing = session.scalars(
                select(Link)
                .where(
                    Link.api_key_id == owner_id,
                    Link.url_hash == digest,
                    Link.is_custom.is_(False),
                    Link.is_active.is_(True),
                    Link.deleted_at.is_(None),
                    Link.expires_at.is_(None),
                )
                .order_by(Link.id)
                .limit(1)
            ).first()
            if existing:
                return existing, False

        link = Link(
            long_url=long_url,
            url_hash=digest,
            api_key_id=owner_id,
            is_custom=req.custom_alias is not None,
            created_at=now,
            expires_at=expires_at,
            click_count=0,
        )
        try:
            if req.custom_alias is not None:
                link.short_code = validate_alias(req.custom_alias)
                session.add(link)
                session.flush()
            else:
                # Placeholder satisfies NOT NULL/UNIQUE until the id-derived code is set,
                # all within one transaction.
                link.short_code = "~" + uuid.uuid4().hex[:31]
                session.add(link)
                session.flush()
                link.short_code = self.codegen.encode(link.id)
                session.flush()
            session.commit()
        except IntegrityError:
            session.rollback()
            if req.custom_alias is not None:
                raise conflict(f"Alias '{req.custom_alias}' is already taken")
            raise
        except AppError:
            session.rollback()
            raise
        return link, True

    # ---- read / update / delete --------------------------------------
    def get_owned(self, session: Session, owner_id: int, code: str) -> Link:
        link = session.scalars(select(Link).where(Link.short_code == code, Link.api_key_id == owner_id)).first()
        if link is None or link.deleted_at is not None:
            raise not_found()
        return link

    def list(self, session: Session, owner_id: int, limit: int, offset: int):
        base = (Link.api_key_id == owner_id, Link.deleted_at.is_(None))
        total = session.scalar(select(func.count()).select_from(Link).where(*base)) or 0
        rows = session.scalars(
            select(Link).where(*base).order_by(Link.created_at.desc(), Link.id.desc()).limit(limit).offset(offset)
        ).all()
        return rows, total

    def update(self, session: Session, owner_id: int, code: str, req: UpdateLinkRequest) -> Link:
        link = self.get_owned(session, owner_id, code)
        now = clock.now()
        fields = req.model_fields_set
        if "is_active" in fields and req.is_active is not None:
            link.is_active = req.is_active
        if req.ttl_seconds is not None or "expires_at" in fields:
            link.expires_at = self._resolve_expiry(req.ttl_seconds, req.expires_at, now)
        session.commit()
        self.cache.delete(link.short_code)
        return link

    def delete(self, session: Session, owner_id: int, code: str) -> None:
        link = self.get_owned(session, owner_id, code)
        link.deleted_at = clock.now()
        link.is_active = False
        session.commit()
        self.cache.delete(link.short_code)

    # ---- redirect resolution -----------------------------------------
    def resolve(self, session: Session, code: str) -> CachedLink:
        """Cache-first lookup for the hot redirect path. Raises 404/410."""
        now = clock.now()
        cached = self.cache.get(code)
        if cached is not None:
            if cached.expires_at is not None and cached.expires_at <= now:
                self.cache.delete(code)
                raise AppError(410, "gone", "This link has expired")
            return cached

        link = session.scalars(select(Link).where(Link.short_code == code)).first()
        if link is None:
            raise not_found()
        state = link_status(link, now)
        if state == "expired":
            raise AppError(410, "gone", "This link has expired")
        if state == "disabled":
            raise AppError(410, "gone", "This link has been disabled or deleted")
        entry = CachedLink(link.id, link.long_url, link.expires_at)
        self.cache.set(code, entry)
        return entry
