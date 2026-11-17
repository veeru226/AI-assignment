# Example Scenarios

Each scenario was produced by running the analyser CLI (`python -m analyst "<requirement>" [--context-dir .]`). Full outputs, regenerable and deterministic, are in [examples/](examples/): `*.md` for reading, `*.json` for machines.

The analyser is intentionally rule-based: the engineer reviews/extends the rules in `analyst/catalog.py`, and AI is used *within* each generated task, not to replace judgement.

## 1. Greenfield

**Input:** `Build a scalable URL shortener service with APIs, persistence, and analytics.`

**Output (summary)** - [full](examples/greenfield.md)
- Classification: **greenfield**, ambiguity score 2 (below blocking threshold 3).
- Capabilities detected: api, persistence, analytics, scalability.
- Ambiguities: "scalable" untestable; no scale target (default assumption: ~1k redirects/s per instance, scale horizontally); datastore unspecified (default: SQLite behind an ORM, PostgreSQL for production); analytics scope undefined (default: totals, time series, referrer, device/browser/OS, country, unique visitors).
- Task breakdown / order: clarify -> design -> scaffold -> persistence + core logic (parallel) -> analytics + scalability -> tests -> security review + docs -> summary. Every task lists the AI assist and how the engineer validates it.
- Risks: functional/design (concurrent writes, sync analytics on request path, privacy of IP/UA, unquantified scale) and AI-related (hallucinated APIs, shallow tests, inefficient patterns, insecure defaults), each with a mitigation.
- **This repository is the execution of this scenario** - see the engineering summary for how each task was carried out.

## 2. Brownfield

**Input:** `Improve the existing analytics: bot traffic such as Googlebot is currently counted in click totals. Exclude bots from totals, with tests.` with `--context-dir .`

**Output (summary)** - [full](examples/brownfield.md)
- Classification: **brownfield** (signals: "existing", "currently", "improve"); the scaffold task is dropped because the project already exists.
- Context scan found the real files involved: `app/analytics.py`, `app/clicks.py`, `app/routes_api.py`, plus tests; frameworks FastAPI/SQLAlchemy/pytest; tests present.
- Order: clarify -> understand existing code -> design the change -> **characterization tests (pin current behaviour)** -> change -> tests -> review -> docs -> summary.
- Trade-off recorded for the change: bots are already stored (`device = "Bot"`), so excluding them at **query time** is reversible, whereas dropping them at write time loses data.

## 3. Ambiguous

**Input:** `Make the system faster and better, with some improvements etc.`

**Output (summary)** - [full](examples/ambiguous.md)
- Classification: **ambiguous** (score 6, likely brownfield); `needs_clarification: true`.
- Ambiguities each with a clarifying question: "faster" (what latency target?), "better" (than what metric?), "improve(ments)" (which metric, baseline -> target?), "some" (which ones?), "etc" (open-ended list).
- The `clarify` task is marked **BLOCKING** - no build task should start until the questions are answered; a performance baseline task is included so any later optimisation is measured.
