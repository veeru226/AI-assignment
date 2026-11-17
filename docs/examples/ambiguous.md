# Requirement Analysis

> Make the system faster and better, with some improvements etc.

**Classification:** ambiguous (likely brownfield, confidence 1.0, ambiguity score 6)  
**Needs clarification before build:** yes  
**Capabilities:** performance

## Engineering problem
Clarify, then deliver to satisfy: "Make the system faster and better, with some improvements etc." Scope capabilities: performance. Open questions to settle first: vague term: 'fast', vague term: 'better', vague term: 'improve', vague term: 'etc', vague term: 'some', existing system context.

## Ambiguities and clarifying questions
- **vague term: 'fast'** - 'fast' is not testable as written. _Q: What latency target (e.g. p95 < 100 ms) counts as fast?_ (default: Pick a conservative measurable target and confirm it.)
- **vague term: 'better'** - 'better' is not testable as written. _Q: Better than what, measured by which metric?_ (default: Pick a conservative measurable target and confirm it.)
- **vague term: 'improve'** - 'improve' is not testable as written. _Q: Which metric should improve, from what baseline to what target?_ (default: Pick a conservative measurable target and confirm it.)
- **vague term: 'etc'** - 'etc' is not testable as written. _Q: The list is open-ended; which items are mandatory?_ (default: Pick a conservative measurable target and confirm it.)
- **vague term: 'some'** - 'some' is not testable as written. _Q: How many / which ones exactly?_ (default: Pick a conservative measurable target and confirm it.)
- **existing system context** - Brownfield work needs the affected code, versions and conventions. _Q: Which module/service is affected, and can the repo be provided (--context-dir)?_ (default: Follow the conventions of the surrounding code once inspected.)

## Assumptions
- Pick a conservative measurable target and confirm it.
- Follow the conventions of the surrounding code once inspected.
- Engineer reviews and owns all AI-generated output; nothing is accepted without running it.

## Task breakdown (engineer-led, AI-assisted)

| # | Task | Phase | Depends on | AI assists with | Validation |
|---|---|---|---|---|---|
| 1 | **Clarify requirements and record assumptions**<br>Resolve open questions, define acceptance criteria and non-goals with the stakeholder. BLOCKING: the requirement is ambiguous; do not start build tasks until answered. | Understand | - | Ask AI to list ambiguities and draft clarifying questions; engineer decides which answers are accepted. | Acceptance criteria are written, measurable and signed off. |
| 2 | **Read existing code and map the affected area**<br>Locate relevant modules, entry points, data flow and existing tests. | Understand | clarify | Use AI to summarise unfamiliar modules and trace call paths; engineer verifies by reading the code. | Short written map of impacted files and invariants. |
| 3 | **Measure baseline and profile hot spots**<br>Benchmark current behaviour so improvements are evidenced. | Test | clarify | AI interprets profiler output; engineer decides what is worth optimising. | Before/after numbers on the same workload. |
| 4 | **Design architecture and data/API contracts**<br>Choose components, data model, API contract and key trade-offs; document decisions. | Design | clarify, understand_code | Use AI to compare design options and draft an OpenAPI/schema; engineer selects and justifies. | Design review: every requirement maps to a component; trade-offs recorded. |
| 5 | **Add characterization tests for current behaviour**<br>Pin existing behaviour before changing it so regressions are detectable. | Test | understand_code | AI generates tests from existing behaviour; engineer removes tests that encode bugs. | Tests pass on the unmodified code. |
| 6 | **Implement the change with minimal blast radius**<br>Apply the enhancement/fix/refactor in small reviewable steps. | Build | characterize | AI proposes diffs; engineer reviews each hunk and rejects unrelated edits. | Diff review; all characterization tests still pass. |
| 7 | **Write unit and integration tests**<br>Cover rules, error paths, persistence and API contract; include negative and boundary cases. | Test | change | AI drafts test cases and fixtures; engineer checks they would fail without the feature (no tautologies). | Coverage report reviewed for meaningful branches; mutation spot-checks. |
| 8 | **Security and performance review**<br>Input validation, injection/SSRF/open-redirect, secrets handling, resource exhaustion, N+1 queries. | Validate | tests | AI acts as reviewer producing a checklist; engineer triages and fixes findings. | Checklist items closed or explicitly accepted as risks. |
| 9 | **Write documentation and API reference**<br>Setup, usage, architecture/trade-offs, known limitations. | Document | tests | AI drafts docs from code; engineer verifies every command and example actually runs. | A new reader can run and evaluate the solution from the README alone. |
| 10 | **Produce final engineering summary**<br>Approach, artifacts, risks, validation results, assumptions and limitations. | Document | docs, security_review | AI structures the summary; engineer owns every claim and its evidence. | Each claim links to a test, measurement or code reference. |

## Execution sequence

1. Wave 1: clarify
2. Wave 2: understand_code, perf_baseline
3. Wave 3: design, characterize
4. Wave 4: change
5. Wave 5: tests
6. Wave 6: security_review, docs
7. Wave 7: summary

## Risks and mitigations

| Category | Risk | Impact | Mitigation |
|---|---|---|---|
| functional | Ambiguous requirement leads to building the wrong thing. | Rework and missed expectations. | Resolve blocking questions first; record assumptions; demo early. |
| design | Optimising without a baseline can target the wrong thing. | Complexity with no gain. | Measure before/after on a representative workload. |
| ai | AI-generated code may contain hallucinated APIs, wrong library versions or subtle logic errors. | Runtime failures or incorrect behaviour that looks plausible. | Run everything; review each hunk; pin dependency versions; prefer small iterative prompts. |
| ai | AI-generated tests can be shallow, tautological or mirror the implementation (coverage gaps). | False confidence; defects escape. | Require negative/boundary cases, confirm tests fail without the change, review coverage by branch. |
| ai | AI tends to over-engineer or pick inefficient patterns (N+1 queries, blocking I/O on hot paths). | Unnecessary complexity or poor performance. | Set explicit non-functional targets, profile/measure, simplify before accepting. |
| ai | AI may suggest insecure defaults (hard-coded secrets, permissive validation). | Vulnerabilities shipped unnoticed. | Security checklist review, secrets via environment, adversarial tests for inputs. |

## Trade-offs

## Validation plan
- Acceptance criteria are written, measurable and signed off.
- Short written map of impacted files and invariants.
- Before/after numbers on the same workload.
- Design review: every requirement maps to a component; trade-offs recorded.
- Tests pass on the unmodified code.
- Diff review; all characterization tests still pass.
- Coverage report reviewed for meaningful branches; mutation spot-checks.
- Checklist items closed or explicitly accepted as risks.
- A new reader can run and evaluate the solution from the README alone.
- Each claim links to a test, measurement or code reference.
- All AI-generated code reviewed line by line and executed before acceptance.
