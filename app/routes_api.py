from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app import clock
from app.analytics import link_stats
from app.auth import create_api_key, get_owner, get_session, require_admin
from app.errors import AppError
from app.models import ApiKey
from app.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    BulkCreateRequest,
    BulkCreateResponse,
    BulkItemResult,
    CreateLinkRequest,
    ErrorBody,
    LinkList,
    LinkOut,
    StatsOut,
    UpdateLinkRequest,
)

router = APIRouter(prefix="/api/v1", tags=["links"])

_ERRORS = {
    401: {"description": "Missing/invalid API key"},
    404: {"description": "Link not found"},
    429: {"description": "Rate limit exceeded (see Retry-After)"},
}


def _service(request: Request):
    """Return the LinkService stored on the app state."""
    return request.app.state.links


@router.post("/keys", response_model=ApiKeyCreated, status_code=201, tags=["admin"], dependencies=[Depends(require_admin)])
def issue_api_key(body: ApiKeyCreate, session: Session = Depends(get_session)):
    """Create an API key (admin only, header `X-Admin-Key`). The key is returned once."""
    record, raw = create_api_key(session, body.name)
    return ApiKeyCreated(id=record.id, name=record.name, prefix=record.prefix, api_key=raw)


@router.post("/links", response_model=LinkOut, status_code=201, responses={200: {"model": LinkOut, "description": "Existing link returned (idempotent)"}, **_ERRORS})
def create_link(
    body: CreateLinkRequest,
    request: Request,
    response: Response,
    owner: ApiKey = Depends(get_owner),
    session: Session = Depends(get_session),
):
    """Create a short link. Re-posting the same URL (no alias/expiry) returns the existing link with 200."""
    svc = _service(request)
    link, created = svc.create(session, owner.id, body)
    if not created:
        response.status_code = 200
    out = svc.to_out(link)
    response.headers["Location"] = out.short_url
    return out


@router.post("/links/bulk", response_model=BulkCreateResponse, responses=_ERRORS)
def bulk_create(
    body: BulkCreateRequest,
    request: Request,
    owner: ApiKey = Depends(get_owner),
    session: Session = Depends(get_session),
):
    """Create up to BULK_MAX_ITEMS links. Items succeed or fail independently."""
    svc = _service(request)
    max_items = request.app.state.settings.bulk_max_items
    if len(body.items) > max_items:
        raise AppError(422, "too_many_items", f"At most {max_items} items per request")
    results: list[BulkItemResult] = []
    for index, item in enumerate(body.items):
        try:
            link, created = svc.create(session, owner.id, item)
            results.append(
                BulkItemResult(index=index, status="created" if created else "existing", link=svc.to_out(link))
            )
        except AppError as exc:
            results.append(BulkItemResult(index=index, status="error", error=ErrorBody(code=exc.code, message=exc.message)))
    return BulkCreateResponse(
        results=results,
        created=sum(r.status == "created" for r in results),
        existing=sum(r.status == "existing" for r in results),
        failed=sum(r.status == "error" for r in results),
    )


@router.get("/links", response_model=LinkList, responses=_ERRORS)
def list_links(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    owner: ApiKey = Depends(get_owner),
    session: Session = Depends(get_session),
):
    # List the owner's links with pagination.
    svc = _service(request)
    rows, total = svc.list(session, owner.id, limit, offset)
    return LinkList(items=[svc.to_out(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/links/{code}", response_model=LinkOut, responses=_ERRORS)
def get_link(code: str, request: Request, owner: ApiKey = Depends(get_owner), session: Session = Depends(get_session)):
    # Return one of the owner's links by short code.
    svc = _service(request)
    return svc.to_out(svc.get_owned(session, owner.id, code))


@router.patch("/links/{code}", response_model=LinkOut, responses=_ERRORS)
def update_link(
    code: str,
    body: UpdateLinkRequest,
    request: Request,
    owner: ApiKey = Depends(get_owner),
    session: Session = Depends(get_session),
):
    """Enable/disable a link or change/clear its expiry."""
    svc = _service(request)
    return svc.to_out(svc.update(session, owner.id, code, body))


@router.delete("/links/{code}", status_code=204, responses=_ERRORS)
def delete_link(code: str, request: Request, owner: ApiKey = Depends(get_owner), session: Session = Depends(get_session)):
    """Soft-delete: the code stops redirecting (410) and click history is retained."""
    _service(request).delete(session, owner.id, code)
    return Response(status_code=204)


def _aware(value: datetime | None) -> datetime | None:
    """Treat naive datetimes as UTC and pass aware ones (or None) through."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@router.get("/links/{code}/stats", response_model=StatsOut, responses=_ERRORS)
def stats(
    code: str,
    request: Request,
    from_: datetime | None = Query(None, alias="from", description="Range start (default: 7 days, or 24h for hourly, before `to`)"),
    to: datetime | None = Query(None, description="Range end (default: now)"),
    granularity: Literal["hour", "day"] = "day",
    top: int = Query(10, ge=1, le=50, description="Max rows per breakdown"),
    owner: ApiKey = Depends(get_owner),
    session: Session = Depends(get_session),
):
    """Click analytics: totals, unique visitors, time series, referrers, browsers, OS, devices, countries.
    Recent clicks may lag by up to ~1s (asynchronous recording)."""
    svc = _service(request)
    link = svc.get_owned(session, owner.id, code)
    end = _aware(to) or clock.now()
    start = _aware(from_) or end - (timedelta(hours=24) if granularity == "hour" else timedelta(days=7))
    return link_stats(session, link, start, end, granularity, top)
