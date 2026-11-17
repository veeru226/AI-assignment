from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime

# BigInteger PKs need an Integer variant on SQLite to keep rowid auto-increment.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    short_code: Mapped[str] = mapped_column(String(32), unique=True)
    long_url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64))
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"))
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    click_count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_clicked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (
        Index("ix_links_owner_urlhash", "api_key_id", "url_hash"),
        Index("ix_links_owner_created", "api_key_id", "created_at"),
    )


class Click(Base):
    """One row per redirect. Bucket columns are precomputed so time-series
    GROUP BY is portable across SQLite/Postgres and can use an index."""

    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id"))
    clicked_at: Mapped[datetime] = mapped_column(UTCDateTime)
    hour_bucket: Mapped[datetime] = mapped_column(UTCDateTime)
    day_bucket: Mapped[date] = mapped_column(Date)
    referrer_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    visitor_hash: Mapped[str] = mapped_column(String(32))

    __table_args__ = (
        Index("ix_clicks_link_hour", "link_id", "hour_bucket"),
        Index("ix_clicks_link_day", "link_id", "day_bucket"),
    )
