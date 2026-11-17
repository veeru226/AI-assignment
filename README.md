# URL Shortener - AI-assisted engineering assignment

A scalable URL shortener (FastAPI + SQLAlchemy) with an API-key protected management API, persistent storage, click analytics, plus a requirement-analysis CLI (`analyst`) that turns a requirement into a task breakdown, risks and assumptions.

| Document | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data model, key decisions and trade-offs, how AI was integrated |
| [docs/ENGINEERING_SUMMARY.md](docs/ENGINEERING_SUMMARY.md) | Approach, artifacts, risks, validation/testing approach, assumptions, limitations |
| [docs/SCENARIOS.md](docs/SCENARIOS.md) | Greenfield / brownfield / ambiguous example inputs and outputs |
| [docs/openapi.json](docs/openapi.json) | API contract (also live at `/docs`) |

## Setup (Windows PowerShell; Python 3.11+)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest                       # 87 tests
$env:ADMIN_API_KEY = "choose-an-admin-secret"           # enables key issuing
.\.venv\Scripts\python -m uvicorn app.main:app_factory --factory --port 8000
```

Linux/macOS: use `.venv/bin/python` and `export`. Interactive docs: <http://localhost:8000/docs>.
(Use another `--port` and `BASE_URL` if 8000 is taken.)

## Try it

```powershell
$base = "http://localhost:8000"
$key = (Invoke-RestMethod -Method Post "$base/api/v1/keys" -Headers @{"X-Admin-Key"="choose-an-admin-secret"} `
        -ContentType "application/json" -Body '{"name":"demo"}').api_key
$h = @{"X-API-Key" = $key}
$link = Invoke-RestMethod -Method Post "$base/api/v1/links" -Headers $h -ContentType "application/json" `
        -Body '{"url":"https://example.com/a/very/long/path?x=1","ttl_seconds":86400}'
$link.short_url                                          # open in a browser -> 302
Invoke-RestMethod "$base/api/v1/links/$($link.short_code)/stats" -Headers $h
```

Without an admin key: `python -m app.manage create-key demo`.

## API summary

| Method & path | Auth | Description |
|---|---|---|
| `GET /{code}` | none | 302 redirect; 404 unknown, 410 expired/disabled/deleted. Click is recorded asynchronously. |
| `POST /api/v1/links` | key | Create. Body: `url`, optional `custom_alias`, `ttl_seconds` or `expires_at`. 201 new, 200 if the same URL already has a link (idempotent), 409 alias taken, 422 invalid. |
| `POST /api/v1/links/bulk` | key | Up to 100 items; per-item `created`/`existing`/`error`. |
| `GET /api/v1/links` | key | Paginated list (`limit`, `offset`). |
| `GET/PATCH/DELETE /api/v1/links/{code}` | key | Read; enable/disable & change/clear expiry; soft delete. |
| `GET /api/v1/links/{code}/stats` | key | `from`, `to`, `granularity=hour|day`, `top`: totals, unique visitors, zero-filled time series, referrers, browsers, OS, devices, countries. |
| `POST /api/v1/keys` | admin key | Issue an API key (shown once; stored hashed). |
| `GET /healthz`, `/readyz` | none | Liveness / readiness (DB ping, cache and click-recorder counters). |

Errors: `{"error": {"code": "...", "message": "..."}}`. Rate-limited calls get `429` + `Retry-After`.

## Requirement-analysis CLI

```powershell
.\.venv\Scripts\python -m analyst "Build a scalable URL shortener service with APIs, persistence, and analytics."
.\.venv\Scripts\python -m analyst "Improve the existing analytics ..." --context-dir . --format json --out plan.json
```

Outputs classification (greenfield/brownfield/ambiguous), ambiguities with clarifying questions, assumptions, dependency-ordered tasks with AI-assist and validation per task, risks (functional/design/AI), trade-offs. Samples in `docs/examples/`.

## Configuration

See [.env.example](.env.example). Production requires `SECRET_KEY`. PostgreSQL: set `DATABASE_URL` and install `psycopg[binary]` (not exercised in this repo's tests, see limitations).

## Load check

`python scripts/bench.py --base http://127.0.0.1:8000 --key <api key>`; see the measured result and caveats in the engineering summary.
