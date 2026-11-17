# Engineering Summary

*AI assists the engineer within tasks; the engineer owns execution and quality.*

## 1. Requirement understanding

Assignment: demonstrate AI-assisted development by turning "Build a scalable URL shortener service with APIs, persistence, and analytics" into a production-quality outcome, with a runnable prototype that also accepts a requirement and produces structured output, an architecture overview, greenfield/brownfield/ambiguous examples, tests, validation, risks, setup and testing documentation.

Ambiguities identified and resolved with the engineer **before** coding (each was a question, not an assumption):

| Open question | Decision |
|---|---|
| Language/framework | Python + FastAPI |
| Datastore | SQLite via SQLAlchemy (swap to PostgreSQL by config) |
| Code generation | Auto-increment id -> keyed permutation -> Base62 (non-enumerable, collision-free) |
| API surface | Custom aliases, expiry, disable/delete, bulk, API keys, rate limiting, idempotent create |
| Redirect type | 302 (every click counted) |
| Analytics | Total clicks, time series (hour/day), referrers, device/browser/OS, country, unique visitors |
| Scalability | Async click recording, LRU redirect cache (Redis-ready seam) |
| "Accepts a requirement" prototype | Deterministic rule-based CLI (no external LLM key) |

Defaults I chose where unspecified (flag if you disagree): GeoIP via trusted proxy header or optional MaxMind DB; production requires `SECRET_KEY`; links are private to the creating API key; private/localhost targets rejected.

## 2. Task decomposition and execution order

| # | Task | Depends on | AI assisted with | Validated by |
|---|---|---|---|---|
| 1 | Clarify requirements/decisions | - | Surfacing ambiguities | Engineer's answers |
| 2 | Design schema, modules, API | 1 | Options & trade-offs | `docs/ARCHITECTURE.md` review |
| 3 | Scaffold, config, DB layer | 2 | Boilerplate | App boots; tests collect |
| 4 | Short-code generator | 3 | Feistel/Base62 drafting | Round-trip, 50k-id uniqueness, range tests |
| 5 | Link service (validation, idempotency, expiry, aliases) | 3,4 | Draft logic | URL/alias unit tests, API tests |
| 6 | Auth + rate limiting | 3 | Draft | Auth/ownership/429 tests |
| 7 | Redirect + cache | 5 | Draft | Cache hit/invalidations/expiry-while-cached tests |
| 8 | Async click recorder + enrichment | 3 | Draft | Batching, drop-on-full, drain-on-stop tests |
| 9 | Analytics API | 8 | Query drafting | Seeded-time-series tests incl. zero fill |
| 10 | Requirement-analysis CLI | - | Rule catalog drafting | 10 analyser tests; three scenario outputs |
| 11 | Live end-to-end + load check | 1-9 | Script | Run against real uvicorn |
| 12 | Docs, OpenAPI export, summary | all | Drafting | Commands executed |

## 3. Generated artifacts

- Code: `app/` (service), `analyst/` (CLI), `scripts/bench.py`.
- API contract: `docs/openapi.json` (generated from the running app, also at `/docs`).
- Tests: `tests/` - 87 tests (unit: codec, URL/alias validation, cache, limiter, UA parsing, analyser; integration: full API with a real SQLite file, restart persistence, analytics aggregates, recorder).
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/SCENARIOS.md`, `docs/examples/*`, this summary.

## 4. Validation and testing approach

- **Automated:** `python -m pytest` -> **87 passed**; line coverage **94%** (`--cov=app --cov=analyst`). Uncovered: the MaxMind reader path and `app/manage.py` CLI (need a GeoIP DB / are thin wrappers), and a few defensive branches.
- **Behavioural focus, not just happy paths:** expiry boundaries using an injected clock (including entries already in the cache), cross-tenant isolation (404), failed-auth throttling, partial-success bulk, soft-delete alias retention, forwarded-header trust on/off, queue overflow, shutdown drain, data surviving an app restart.
- **Live check:** real `uvicorn`, created a key and link with HTTP calls, redirected with a mobile User-Agent and referrer, confirmed stats showed referrer host `news.ycombinator.com`, OS `iOS`, device `Mobile`.
- **Load check** (`scripts/bench.py`, 16 client threads, 8s, same Windows machine, 1 uvicorn process, SQLite): ~600 redirects/s, p50 ≈ 21 ms, p95 ≈ 62 ms, **0 errors, and 4,764/4,764 clicks recorded**. The Python threaded client on the same machine is itself the bottleneck, so this proves correctness under concurrency, **not** capacity. A real capacity claim needs a dedicated load generator and Postgres.

### Defects found by validation/review (and fixed)
1. Draft placeholder short code derived from the URL hash would collide for concurrent first-time creates of the same URL by different owners -> switched to a random placeholder (found during code review, before it was exercised).
2. OpenAPI "Duplicate Operation ID" warning from registering GET+HEAD together -> split into two routes (HEAD hidden from schema and, by design, not counted as a click).
3. Analyser false positive: the word "traffic" (bot *traffic*) triggered the *scalability* capability and made a clear brownfield requirement look ambiguous -> keyword narrowed to "high traffic"; found by a failing test.
4. Benchmark script crashed at the end on a keep-alive connection that had idled out -> fresh connection.
5. Port 8000 was occupied on the dev machine -> README documents `--port`/`BASE_URL`.

## 5. Risks, trade-offs and mitigations

| Category | Risk | Mitigation / status |
|---|---|---|
| Functional | Click loss on crash or queue overflow | Bounded queue, drain on shutdown, `dropped` counter on `/readyz`; durable broker is the upgrade |
| Functional | Duplicate links from simultaneous identical creates | Harmless; documented; unique index would need a partial-index design |
| Functional | Stale redirects across instances after disable/delete | TTL-bounded; Redis cache is the upgrade |
| Functional | Clock/UTC edge cases for expiry | UTC everywhere, injected clock in tests |
| Design | SQLite single-writer | WAL mode; Postgres via `DATABASE_URL` (see limitations) |
| Design | Large-link analytics scan the raw `clicks` table | Indexed bucket columns; rollup table is the next step |
| Design | Per-process rate limiter/cache | Seams (Protocols) for shared backends |
| Security | Open redirect/phishing abuse | Only http(s), no credentials, no private targets, no self-links, authenticated creation, rate limits; reputation scanning not implemented |
| Security | Key theft/guessing | 256-bit keys stored hashed; failed auth throttled per IP; production refuses default secret |
| Privacy | IP/UA are personal data | Raw IP never stored (HMAC only); referrer reduced to host; UA reduced to family names |
| AI | Hallucinated APIs / wrong versions | Everything executed; dependency versions installed and checked (e.g. SQLAlchemy 2.x, Starlette 1.x APIs verified by tests) |
| AI | Shallow or tautological tests | Tests assert behaviours (boundaries, isolation, failure) rather than restating code; defect #3 above was caught by a test |
| AI | Over-engineering / inefficiency | Deliberately small surface; measured instead of assumed; no Alembic/Redis added without need |
| AI | Insecure defaults | Dev secret rejected in production; forwarded headers ignored unless trusted |

## 6. Assumptions and limitations

Assumptions: single region; UTC; JSON/REST; callers are API-key holders; analytics freshness of ~1s is acceptable; "unique visitor" means distinct client IP.

Known limitations (honest list):
- PostgreSQL support is by design (portable SQL, no dialect functions) but **not tested here** - Docker/Postgres were not available. SQLite is what the tests exercise.
- No schema migrations (tables are created at startup); adopt Alembic before changing schemas in production.
- Per-process cache and limiter; redirects themselves are not rate limited (CDN/WAF job).
- No API-key revoke/rotate endpoint; no link-click limits; no QR codes/UI.
- MaxMind lookup is implemented but untested (no database file in the environment); header-based country is tested.
- Unique visitors use IP only (NAT under-counts); hash is not rotated.
- Capacity of the generator is 2^40 links; changing `SECRET_KEY` changes codes issued afterwards.
- Hostnames resolving to private addresses are not blocked (no DNS lookup by design, to avoid SSRF-style resolver coupling and latency).
- `httpx`-based `TestClient` emits a Starlette deprecation notice (cosmetic; `httpx2` is the successor).

## 7. Engineer ownership checklist (for the candidate)

Before presenting, be ready to explain and, ideally, re-derive: the Feistel construction and why it is a bijection (`app/codegen.py`); why `short_code` is looked up by index rather than decoded; the async recorder's guarantees and failure modes (`app/clicks.py`); why 302 and why HEAD is not counted; cache invalidation rules; and which analyser rules you would change (`analyst/catalog.py`). Run `pytest` and the live walkthrough in the README yourself, and read every module once - the assignment grades ownership of AI-assisted code.
