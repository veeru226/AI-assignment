# Architecture

## Overview

```
                 +-------------------------------------------+
 client --GET /abc--> FastAPI (stateless)                      |
                 |  redirect: LRU cache --miss--> DB lookup    |
                 |      |  put_nowait(ClickEvent)              |
                 |      v                                      |
                 |  bounded queue --> ClickRecorder thread ----+--> clicks table
                 |                    (batch, enrich, 1 txn)   |    links.click_count
 client --/api/v1--> auth (API key) -> rate limit -> LinkService -> links/api_keys tables
                 +-------------------------------------------+
```

| Module | Responsibility |
|---|---|
| `app/main.py` | App factory, lifespan (create tables, start/stop recorder), error handlers |
| `app/routes_api.py`, `routes_redirect.py` | HTTP layer only: parse, call service, shape response |
| `app/service.py` | Link rules: normalise/validate, idempotency, aliases, expiry, state, cache-first resolve |
| `app/codegen.py` | Id -> short code (keyed Feistel permutation + Base62) |
| `app/clicks.py` | Async batched click persistence |
| `app/analytics.py` | Aggregation queries |
| `app/cache.py`, `ratelimit.py`, `geo.py` | Replaceable seams (Protocols) for Redis-style backends / GeoIP |
| `app/auth.py` | API-key auth, admin auth, rate-limit hook |
| `analyst/` | Rule-based requirement analyser CLI |

## Data model

- `api_keys(id, name, prefix, key_hash UNIQUE, is_active, created_at)` - owner/tenant.
- `links(id, short_code UNIQUE, long_url, url_hash, api_key_id, is_custom, is_active, created_at, expires_at, deleted_at, click_count, last_clicked_at)`; indexes `(api_key_id, url_hash)` for idempotency lookups and `(api_key_id, created_at)` for listing.
- `clicks(id, link_id, clicked_at, hour_bucket, day_bucket, referrer_host, browser, os, device, country, visitor_hash)`; indexes `(link_id, hour_bucket)`, `(link_id, day_bucket)`.

## Key decisions and trade-offs

| Decision | Why | Trade-off / alternative |
|---|---|---|
| **Short code = keyed Feistel permutation of the auto-increment id, Base62, fixed 7 chars** (your choice) | No collisions or retries by construction, safe across instances, codes aren't enumerable; lookup uses the indexed `short_code`. | Capacity 2^40 (~1.1e12) links. Obfuscation, not secrecy: a leaked `SECRET_KEY` allows enumeration, and rotating it changes all future codes (existing ones keep working since they're stored). |
| Custom aliases may not be exactly 7 alphanumerics | A vanity alias can never collide with a future generated code. | Slightly restrictive aliases. |
| **302**, not 301 (your choice) | Browsers don't cache, so every click reaches us and is counted; links can be disabled/expired. | More redirect traffic than a 301. |
| **Click recording off the request path**: bounded in-memory queue + one writer thread, batched transactions | Redirect latency is independent of DB writes; batching amortises commits (500/txn). | Crash loses up to ~0.5s of clicks; full queue drops (counted in `/readyz`). Upgrade path: Kafka/SQS/Redis Streams. |
| Redirect path: LRU cache (TTL 300s) in front of DB; hit needs **no DB access** | Redirects are read-heavy; a cache hit should skip the DB entirely. | Per-process cache: disable/delete is instant on the instance that handled it, but other instances may serve stale up to TTL. `Cache` Protocol is the seam for Redis. |
| `click_count` counter on `links` updated in the batch writer + raw `clicks` rows | O(1) total for list/detail; raw rows for segmentation. | Counter and rows are in one transaction so they agree. |
| Precomputed `hour_bucket`/`day_bucket` columns | Portable GROUP BY (SQLite/Postgres), index-friendly, no dialect-specific date functions. | Small extra storage; buckets are UTC. |
| Unique visitors = HMAC(secret, IP) truncated | No raw IPs stored (privacy), still countable. | Shared IPs (NAT) under-count; one person on many IPs over-counts. No rotation of the hash. |
| Country: trusted CDN header (`CF-IPCountry`) -> optional MaxMind DB -> `unknown` | No mandatory external data file; header only trusted when `TRUST_PROXY_HEADERS=true`. | Accuracy depends on the proxy/DB. |
| API keys: random 256-bit, stored as SHA-256 | A fast hash is fine for high-entropy secrets; constant lookup by hash. | No key rotation/revocation endpoint yet (`is_active` exists). |
| Ownership: foreign links return **404**, not 403 | Doesn't reveal which codes exist. | Slightly harder debugging. |
| Soft delete; deleted codes stay reserved | Click history retained; no one can hijack a retired alias. | Aliases can't be reused. |
| Idempotent create keyed on (owner, normalised URL), only when no alias/TTL requested | Retries are safe and storage doesn't bloat. | Not enforced by a unique index, so two truly concurrent first-time requests may create two codes (harmless). |
| Token-bucket rate limit per API key; failed auth throttled per IP | Smooth bursts, cheap, bounded memory (LRU of 100k buckets). | Per-process: effective limit scales with instance count. |
| URL safety: http/https only, no credentials, no localhost/private IPs, no self-links, max 2048 chars | Reduces phishing/abuse and internal-target links (config `ALLOW_PRIVATE_TARGETS`). | Doesn't check hostnames that *resolve* to private IPs or reputation (e.g. Safe Browsing). |
| SQLite (WAL) via SQLAlchemy by default | Zero setup; evaluator can run instantly; swap by `DATABASE_URL`. | Single writer; Postgres recommended for production. |
| Sync endpoints + sync SQLAlchemy | Simple, correct; FastAPI runs them in a thread pool. | An async stack could squeeze more concurrency per process. |

## Scaling path

1. Run N stateless instances behind a load balancer (`uvicorn --workers`), PostgreSQL primary + replicas for stats reads.
2. Replace `LRUCache` / `TokenBucketLimiter` with Redis implementations of the same Protocols.
3. Replace the in-memory click queue with a durable stream and a separate consumer.
4. Roll up `clicks` into daily aggregates (or partition by month) once per-link volume is large; archive raw rows.
5. Put a CDN/WAF in front for redirect rate limiting and geo headers.

## How AI is integrated into the development tasks

AI (Copilot agent) accelerated each task, while the engineer set requirements/decisions and accepted or rejected output:

| Task | AI assisted with | Engineer decision / ownership |
|---|---|---|
| Requirement understanding | Extracted requirements from the assignment pages; proposed the design questions | Engineer chose: FastAPI, SQLite, Feistel codes, all API/analytics features, 302, async clicks, LRU cache, rule-based analyser |
| Design | Drafted schema, module layout, trade-off options | Engineer picked options; trade-offs recorded above |
| Implementation | Generated modules, schemas, routes | Reviewed, corrected defects found while validating (see engineering summary) |
| Tests | Drafted unit/integration tests | Engineer-defined behaviours (boundaries, isolation, failure paths); tests run and green |
| Debugging/refactor | Diagnosed warnings and a classifier false-positive | Verified by re-running tests |
| Documentation | Drafted README/docs | Commands were executed to verify them |
