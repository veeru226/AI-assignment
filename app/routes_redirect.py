from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import clock
from app.auth import client_ip, get_session
from app.clicks import ClickEvent
from app.errors import not_found
from app.urlutil import ALIAS_RE

router = APIRouter()


@router.get("/healthz", tags=["ops"])
def healthz():
    # Liveness probe: always reports ok.
    return {"status": "ok"}


@router.get("/readyz", tags=["ops"])
def readyz(request: Request, session: Session = Depends(get_session)):
    # Readiness probe: checks the database and reports cache and click counters.
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "database_unavailable"}, status_code=503)
    state = request.app.state
    return {
        "status": "ready",
        "cache": {"entries": len(state.cache), "hits": state.cache.hits, "misses": state.cache.misses},
        "clicks": {"recorded": state.recorder.recorded, "dropped": state.recorder.dropped},
    }


@router.head("/{code}", include_in_schema=False)  # HEAD is served but not counted as a click
@router.get("/{code}", tags=["redirect"],
            responses={302: {"description": "Redirect to the destination"}, 404: {}, 410: {"description": "Expired, disabled or deleted"}})
def redirect(code: str, request: Request, session: Session = Depends(get_session)):
    """Public redirect. Click recording is queued and never blocks the response."""
    if not ALIAS_RE.match(code):
        raise not_found()
    entry = request.app.state.links.resolve(session, code)
    if request.method == "GET":
        headers = request.headers
        request.app.state.recorder.record(
            ClickEvent(
                link_id=entry.link_id,
                clicked_at=clock.now(),
                ip=client_ip(request),
                user_agent=headers.get("user-agent"),
                referrer=headers.get("referer"),
                country_hint=headers.get("cf-ipcountry") or headers.get("x-country-code")
                if request.app.state.settings.trust_proxy_headers
                else None,
            )
        )
    return RedirectResponse(entry.long_url, status_code=302, headers={"Cache-Control": "private, max-age=0"})
