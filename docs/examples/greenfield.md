# Requirement Analysis

> Build a scalable URL shortener service with APIs, persistence, and analytics.

**Classification:** greenfield (likely greenfield, confidence 1.0, ambiguity score 2)  
**Needs clarification before build:** no  
**Capabilities:** api, persistence, analytics, scalability

## Engineering problem
Design and build a new system to satisfy: "Build a scalable URL shortener service with APIs, persistence, and analytics." Scope capabilities: api, persistence, analytics, scalability. Open questions to settle first: vague term: 'scalable', scale target.

## Ambiguities and clarifying questions
- **vague term: 'scalable'** - 'scalable' is not testable as written. _Q: What load must it handle (requests/sec, records, users) and over what time horizon?_ (default: Pick a conservative measurable target and confirm it.)
- **scale target** - Scalability is requested without numbers. _Q: Expected peak requests/sec, total records, read:write ratio, growth rate?_ (default: Design for ~1k redirects/sec per instance and horizontal scale-out.)
- **datastore choice** - No datastore specified. _Q: Is there a mandated database, or operational constraints (managed service, no Docker)?_ (default: SQLite for the prototype behind an ORM, PostgreSQL for production.)
- **analytics scope** - 'Analytics' can mean totals, time series, or segmentation. _Q: Which dimensions (time, referrer, device, geo, unique visitors), freshness and retention?_ (default: Totals, time series, referrer, device/browser/OS, country, unique visitors.)

## Assumptions
- Interface is a JSON/REST HTTP API with an OpenAPI contract.
- A relational database is acceptable; schema evolves via migrations.
- Analytics are near-real-time (seconds), aggregated per link, and identifiers are hashed for privacy.
- Horizontal scaling of stateless instances behind a load balancer; numeric targets are to be confirmed.
- Pick a conservative measurable target and confirm it.
- Design for ~1k redirects/sec per instance and horizontal scale-out.
- SQLite for the prototype behind an ORM, PostgreSQL for production.
- Totals, time series, referrer, device/browser/OS, country, unique visitors.
- Engineer reviews and owns all AI-generated output; nothing is accepted without running it.

## Task breakdown (engineer-led, AI-assisted)

| # | Task | Phase | Depends on | AI assists with | Validation |
|---|---|---|---|---|---|
| 1 | **Clarify requirements and record assumptions**<br>Resolve open questions, define acceptance criteria and non-goals with the stakeholder. | Understand | - | Ask AI to list ambiguities and draft clarifying questions; engineer decides which answers are accepted. | Acceptance criteria are written, measurable and signed off. |
| 2 | **Design architecture and data/API contracts**<br>Choose components, data model, API contract and key trade-offs; document decisions. | Design | clarify | Use AI to compare design options and draft an OpenAPI/schema; engineer selects and justifies. | Design review: every requirement maps to a component; trade-offs recorded. |
| 3 | **Scaffold project, configuration and tooling**<br>Project layout, dependency management, config via environment, lint/test tooling. | Build | design | AI generates boilerplate; engineer prunes unused dependencies and checks versions exist. | Clean checkout installs and runs the (empty) test suite. |
| 4 | **Implement persistent storage layer**<br>Schema, indexes, constraints and data-access code; migrations strategy. | Build | design, scaffold | AI drafts models and queries; engineer reviews indexes, constraints and transaction boundaries. | Integration tests against a real database; data survives restart. |
| 5 | **Implement core domain logic and API endpoints**<br>Request validation, business rules, error model and endpoint handlers. | Build | design, scaffold | AI generates handlers and validators; engineer verifies edge cases and error semantics. | Unit tests for rules; API tests for status codes and error bodies. |
| 6 | **Implement event capture and analytics queries**<br>Capture events off the hot path, enrich, aggregate by time and dimension. | Build | persistence, core_logic | AI drafts aggregation queries; engineer checks time-zone, bucketing and index use. | Seeded-data tests with known aggregates; query plan check on large data. |
| 7 | **Address scalability: statelessness, async work, limits**<br>Keep app stateless, move slow work off the request path, identify bottlenecks. | Build | core_logic, persistence | AI proposes bottlenecks and fixes; engineer validates with measurements, not assumptions. | Load test with stated target; document measured throughput and limits. |
| 8 | **Write unit and integration tests**<br>Cover rules, error paths, persistence and API contract; include negative and boundary cases. | Test | scaffold, persistence, core_logic, analytics, scalability | AI drafts test cases and fixtures; engineer checks they would fail without the feature (no tautologies). | Coverage report reviewed for meaningful branches; mutation spot-checks. |
| 9 | **Security and performance review**<br>Input validation, injection/SSRF/open-redirect, secrets handling, resource exhaustion, N+1 queries. | Validate | tests | AI acts as reviewer producing a checklist; engineer triages and fixes findings. | Checklist items closed or explicitly accepted as risks. |
| 10 | **Write documentation and API reference**<br>Setup, usage, architecture/trade-offs, known limitations. | Document | tests | AI drafts docs from code; engineer verifies every command and example actually runs. | A new reader can run and evaluate the solution from the README alone. |
| 11 | **Produce final engineering summary**<br>Approach, artifacts, risks, validation results, assumptions and limitations. | Document | docs, security_review | AI structures the summary; engineer owns every claim and its evidence. | Each claim links to a test, measurement or code reference. |

## Execution sequence

1. Wave 1: clarify
2. Wave 2: design
3. Wave 3: scaffold
4. Wave 4: persistence, core_logic
5. Wave 5: analytics, scalability
6. Wave 6: tests
7. Wave 7: security_review, docs
8. Wave 8: summary

## Risks and mitigations

| Category | Risk | Impact | Mitigation |
|---|---|---|---|
| functional | Ambiguous requirement leads to building the wrong thing. | Rework and missed expectations. | Resolve blocking questions first; record assumptions; demo early. |
| design | Schema/index choices may not suit query patterns as data grows. | Slow queries, painful migrations. | Model access patterns first; index for them; plan migrations (Alembic). |
| functional | Concurrent writes can create duplicates or lose updates. | Data integrity issues. | Use DB constraints and transactions; test concurrent paths. |
| design | Writing analytics synchronously on the request path adds latency and couples availability. | Slow user-facing requests. | Queue events and batch-write; accept bounded loss or use a durable broker. |
| functional | Privacy: raw IPs/user agents are personal data. | Compliance exposure. | Hash/minimise identifiers, define retention, document. |
| design | Scalability target is unquantified so the design may be over- or under-built. | Wasted effort or outage under load. | Agree numeric targets; load-test; document measured limits. |
| ai | AI-generated code may contain hallucinated APIs, wrong library versions or subtle logic errors. | Runtime failures or incorrect behaviour that looks plausible. | Run everything; review each hunk; pin dependency versions; prefer small iterative prompts. |
| ai | AI-generated tests can be shallow, tautological or mirror the implementation (coverage gaps). | False confidence; defects escape. | Require negative/boundary cases, confirm tests fail without the change, review coverage by branch. |
| ai | AI tends to over-engineer or pick inefficient patterns (N+1 queries, blocking I/O on hot paths). | Unnecessary complexity or poor performance. | Set explicit non-functional targets, profile/measure, simplify before accepting. |
| ai | AI may suggest insecure defaults (hard-coded secrets, permissive validation). | Vulnerabilities shipped unnoticed. | Security checklist review, secrets via environment, adversarial tests for inputs. |

## Trade-offs
- SQLite is zero-setup but single-writer; PostgreSQL scales better at the cost of operating a server.
- Asynchronous event capture keeps the hot path fast but can lose in-flight events on a crash; durable queues cost complexity.
- Stateless instances scale horizontally, but per-process caches/limiters then need shared backends.

## Validation plan
- Acceptance criteria are written, measurable and signed off.
- Design review: every requirement maps to a component; trade-offs recorded.
- Clean checkout installs and runs the (empty) test suite.
- Integration tests against a real database; data survives restart.
- Unit tests for rules; API tests for status codes and error bodies.
- Seeded-data tests with known aggregates; query plan check on large data.
- Load test with stated target; document measured throughput and limits.
- Coverage report reviewed for meaningful branches; mutation spot-checks.
- Checklist items closed or explicitly accepted as risks.
- A new reader can run and evaluate the solution from the README alone.
- Each claim links to a test, measurement or code reference.
- All AI-generated code reviewed line by line and executed before acceptance.
