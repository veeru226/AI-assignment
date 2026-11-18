from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _require_aware(value: datetime | None) -> datetime | None:
    """Return the value, raising ValueError if it is a naive datetime."""
    if value is not None and value.tzinfo is None:
        raise ValueError("datetime must include a timezone offset, e.g. 2030-01-01T00:00:00Z")
    return value


class CreateLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="Destination http(s) URL", examples=["https://example.com/some/long/path?x=1"])
    custom_alias: str | None = Field(default=None, description="Optional vanity code, 3-32 chars [A-Za-z0-9_-]")
    ttl_seconds: int | None = Field(default=None, gt=0, description="Expire this many seconds from now")
    expires_at: datetime | None = Field(default=None, description="Absolute expiry (timezone required)")

    @model_validator(mode="after")
    def _check(self):
        """Reject requests that set both ttl_seconds and expires_at, or a naive expires_at."""
        if self.ttl_seconds is not None and self.expires_at is not None:
            raise ValueError("provide either ttl_seconds or expires_at, not both")
        _require_aware(self.expires_at)
        return self


class UpdateLinkRequest(BaseModel):
    """PATCH semantics: omitted fields are unchanged; `expires_at: null` clears expiry."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    expires_at: datetime | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check(self):
        """Reject conflicting expiry fields, a naive expires_at, or an empty update."""
        if self.ttl_seconds is not None and "expires_at" in self.model_fields_set:
            raise ValueError("provide either ttl_seconds or expires_at, not both")
        _require_aware(self.expires_at)
        if not self.model_fields_set:
            raise ValueError("no fields to update")
        return self


class LinkOut(BaseModel):
    short_code: str
    short_url: str
    long_url: str
    is_custom: bool
    is_active: bool
    status: Literal["active", "expired", "disabled"]
    created_at: datetime
    expires_at: datetime | None
    click_count: int
    last_clicked_at: datetime | None


class LinkList(BaseModel):
    items: list[LinkOut]
    total: int
    limit: int
    offset: int


class BulkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CreateLinkRequest] = Field(min_length=1)


class ErrorBody(BaseModel):
    code: str
    message: str


class BulkItemResult(BaseModel):
    index: int
    status: Literal["created", "existing", "error"]
    link: LinkOut | None = None
    error: ErrorBody | None = None


class BulkCreateResponse(BaseModel):
    results: list[BulkItemResult]
    created: int
    existing: int
    failed: int


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


class ApiKeyCreated(BaseModel):
    id: int
    name: str
    prefix: str
    api_key: str = Field(description="Shown once; only a hash is stored")


class CountItem(BaseModel):
    value: str
    clicks: int


class TimeBucket(BaseModel):
    bucket: datetime
    clicks: int


class StatsOut(BaseModel):
    short_code: str
    total_clicks: int = Field(description="All-time clicks (maintained counter)")
    range_start: datetime
    range_end: datetime
    granularity: Literal["hour", "day"]
    clicks_in_range: int
    unique_visitors_in_range: int
    timeseries: list[TimeBucket]
    referrers: list[CountItem]
    browsers: list[CountItem]
    operating_systems: list[CountItem]
    devices: list[CountItem]
    countries: list[CountItem]


MAX_HOURLY_RANGE = timedelta(days=31)
MAX_DAILY_RANGE = timedelta(days=366)
