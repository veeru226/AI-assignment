# Requirement Analysis

> Improve the existing analytics: bot traffic such as Googlebot is currently counted in click totals. Exclude bots from totals, with tests.

**Classification:** brownfield (likely brownfield, confidence 1.0, ambiguity score 1)  
**Needs clarification before build:** no  
**Capabilities:** analytics, testing

## Engineering problem
Change an existing system to satisfy: "Improve the existing analytics: bot traffic such as Googlebot is currently counted in click totals. Exclude bots from totals, with tests." Scope capabilities: analytics, testing. Open questions to settle first: vague term: 'improve'.

## Existing code context
- Files scanned: 46; languages: {'.py': 34}
- Frameworks: fastapi, sqlalchemy; tests present: True
- Likely relevant files: tests\test_redirect_analytics.py, analyst\catalog.py, app\analytics.py, tests\test_analyst.py, app\clicks.py, analyst\analyzer.py, tests\test_clicks.py, app\routes_api.py

## Ambiguities and clarifying questions
- **vague term: 'improve'** - 'improve' is not testable as written. _Q: Which metric should improve, from what baseline to what target?_ (default: Pick a conservative measurable target and confirm it.)
- **analytics scope** - 'Analytics' can mean totals, time series, or segmentation. _Q: Which dimensions (time, referrer, device, geo, unique visitors), freshness and retention?_ (default: Totals, time series, referrer, device/browser/OS, country, unique visitors.)

## Assumptions
- Analytics are near-real-time (seconds), aggregated per link, and identifiers are hashed for privacy.
- Pick a conservative measurable target and confirm it.
- Totals, time series, referrer, device/browser/OS, country, unique visitors.
- Engineer reviews and owns all AI-generated output; nothing is accepted without running it.

## Task breakdown (engineer-led, AI-assisted)

| # | Task | Phase | Depends on | AI assists with | Validation |
|---|---|---|---|---|---|
| 1 | **Clarify requirements and record assumptions**<br>Resolve open questions, define acceptance criteria and non-goals with the stakeholder. | Understand | - | Ask AI to list ambiguities and draft clarifying questions; engineer decides which answers are accepted. | Acceptance criteria are written, measurable and signed off. |
| 2 | **Read existing code and map the affected area**<br>Locate relevant modules, entry points, data flow and existing tests. | Understand | clarify | Use AI to summarise unfamiliar modules and trace call paths; engineer verifies by reading the code. | Short written map of impacted files and invariants. |
| 3 | **Design architecture and data/API contracts**<br>Choose components, data model, API contract and key trade-offs; document decisions. | Design | clarify, understand_code | Use AI to compare design options and draft an OpenAPI/schema; engineer selects and justifies. | Design review: every requirement maps to a component; trade-offs recorded. |
| 4 | **Add characterization tests for current behaviour**<br>Pin existing behaviour before changing it so regressions are detectable. | Test | understand_code | AI generates tests from existing behaviour; engineer removes tests that encode bugs. | Tests pass on the unmodified code. |
| 5 | **Implement event capture and analytics queries**<br>Capture events off the hot path, enrich, aggregate by time and dimension. | Build | characterize | AI drafts aggregation queries; engineer checks time-zone, bucketing and index use. | Seeded-data tests with known aggregates; query plan check on large data. |
| 6 | **Implement the change with minimal blast radius**<br>Apply the enhancement/fix/refactor in small reviewable steps. | Build | characterize | AI proposes diffs; engineer reviews each hunk and rejects unrelated edits. | Diff review; all characterization tests still pass. |
| 7 | **Write unit and integration tests**<br>Cover rules, error paths, persistence and API contract; include negative and boundary cases. | Test | analytics, change | AI drafts test cases and fixtures; engineer checks they would fail without the feature (no tautologies). | Coverage report reviewed for meaningful branches; mutation spot-checks. |
| 8 | **Security and performance review**<br>Input validation, injection/SSRF/open-redirect, secrets handling, resource exhaustion, N+1 queries. | Validate | tests | AI acts as reviewer producing a checklist; engineer triages and fixes findings. | Checklist items closed or explicitly accepted as risks. |
| 9 | **Write documentation and API reference**<br>Setup, usage, architecture/trade-offs, known limitations. | Document | tests | AI drafts docs from code; engineer verifies every command and example actually runs. | A new reader can run and evaluate the solution from the README alone. |
| 10 | **Produce final engineering summary**<br>Approach, artifacts, risks, validation results, assumptions and limitations. | Document | docs, security_review | AI structures the summary; engineer owns every claim and its evidence. | Each claim links to a test, measurement or code reference. |

## Execution sequence

1. Wave 1: clarify
2. Wave 2: understand_code
3. Wave 3: design, characterize
4. Wave 4: analytics, change
5. Wave 5: tests
6. Wave 6: security_review, docs
7. Wave 7: summary

## Risks and mitigations

| Category | Risk | Impact | Mitigation |
|---|---|---|---|
| functional | Ambiguous requirement leads to building the wrong thing. | Rework and missed expectations. | Resolve blocking questions first; record assumptions; demo early. |
| design | Writing analytics synchronously on the request path adds latency and couples availability. | Slow user-facing requests. | Queue events and batch-write; accept bounded loss or use a durable broker. |
| functional | Privacy: raw IPs/user agents are personal data. | Compliance exposure. | Hash/minimise identifiers, define retention, document. |
| ai | AI-generated code may contain hallucinated APIs, wrong library versions or subtle logic errors. | Runtime failures or incorrect behaviour that looks plausible. | Run everything; review each hunk; pin dependency versions; prefer small iterative prompts. |
| ai | AI-generated tests can be shallow, tautological or mirror the implementation (coverage gaps). | False confidence; defects escape. | Require negative/boundary cases, confirm tests fail without the change, review coverage by branch. |
| ai | AI tends to over-engineer or pick inefficient patterns (N+1 queries, blocking I/O on hot paths). | Unnecessary complexity or poor performance. | Set explicit non-functional targets, profile/measure, simplify before accepting. |
| ai | AI may suggest insecure defaults (hard-coded secrets, permissive validation). | Vulnerabilities shipped unnoticed. | Security checklist review, secrets via environment, adversarial tests for inputs. |

## Trade-offs
- Asynchronous event capture keeps the hot path fast but can lose in-flight events on a crash; durable queues cost complexity.

## Validation plan
- Acceptance criteria are written, measurable and signed off.
- Short written map of impacted files and invariants.
- Design review: every requirement maps to a component; trade-offs recorded.
- Tests pass on the unmodified code.
- Seeded-data tests with known aggregates; query plan check on large data.
- Diff review; all characterization tests still pass.
- Coverage report reviewed for meaningful branches; mutation spot-checks.
- Checklist items closed or explicitly accepted as risks.
- A new reader can run and evaluate the solution from the README alone.
- Each claim links to a test, measurement or code reference.
- All AI-generated code reviewed line by line and executed before acceptance.
