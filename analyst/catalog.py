"""Rule catalog for the requirement analyser.

Everything here is plain data so an engineer can review and extend it; the
analyser stays deterministic (same input -> same output), which makes its output
testable and defensible, unlike free-form LLM text.
"""

# capability -> keywords (matched on word stems, case-insensitive)
CAPABILITIES: dict[str, tuple[str, ...]] = {
    "api": ("api", "endpoint", "rest", "http", "service", "webhook", "graphql"),
    "persistence": ("persist", "database", "storage", "store", "sql", "postgres", "mysql", "sqlite", "mongo", "save", "record"),
    "analytics": ("analytic", "metric", "statistic", "stats", "track", "report", "dashboard", "insight"),
    "auth": ("auth", "login", "api key", "token", "permission", "oauth", "role", "secure", "security"),
    "caching": ("cache", "caching", "redis", "memcache", "latency"),
    "scalability": ("scalab", "scale", "throughput", "high availability", "concurren", "load", "million", "high traffic"),
    "rate_limiting": ("rate limit", "throttl", "abuse", "quota"),
    "expiry": ("expire", "expiry", "expiration", "ttl", "time-to-live"),
    "bulk": ("bulk", "batch", "import"),
    "ui": ("ui", "frontend", "web page", "dashboard", "screen", "form"),
    "bugfix": ("bug", "fix", "defect", "crash", "error", "regression", "broken", "incorrect", "wrong", "fails", "failing"),
    "refactor": ("refactor", "clean up", "restructure", "modulari", "tech debt", "simplif"),
    "performance": ("performance", "optimi", "slow", "speed up", "faster", "latency"),
    "testing": ("test", "coverage", "qa"),
    "documentation": ("document", "docs", "readme", "swagger", "openapi"),
}

GREENFIELD_SIGNALS = ("build", "create", "develop", "implement", "design", "new ", "from scratch", "greenfield", "introduce", "set up", "setup")
BROWNFIELD_SIGNALS = (
    "existing", "currently", "legacy", "refactor", "fix", "bug", "enhance", "improve", "migrate", "upgrade",
    "optimi", "regression", "broken", "instead of", "change the", "update the", "add to", "extend", "already",
)

# Words that sound like requirements but cannot be tested without a number or definition.
VAGUE_TERMS = {
    "fast": "What latency target (e.g. p95 < 100 ms) counts as fast?",
    "quick": "What response time counts as quick?",
    "scalable": "What load must it handle (requests/sec, records, users) and over what time horizon?",
    "secure": "What threats or compliance standards are in scope (OWASP, PII, SOC2)?",
    "robust": "Which failure modes must it tolerate (DB outage, bad input, duplicate requests)?",
    "reliable": "What availability/durability target is expected (e.g. 99.9%)?",
    "simple": "Who is the user and what is the primary workflow that must be simple?",
    "user-friendly": "Which users, and what usability criteria would show it is friendly?",
    "efficient": "Efficient in which dimension: CPU, memory, cost, developer effort?",
    "better": "Better than what, measured by which metric?",
    "improve": "Which metric should improve, from what baseline to what target?",
    "modern": "Which concrete technologies or practices are expected?",
    "etc": "The list is open-ended; which items are mandatory?",
    "some": "How many / which ones exactly?",
    "optimize": "Optimise for which resource and what target?",
    "easy": "Easy for whom, and measured how?",
    "good": "What is the acceptance criterion for 'good'?",
}

SCALE_HINT = ("million", "thousand", "per second", "rps", "qps", "tps", "users", "requests", "req/s", "k/s")

# Each task: (key, title, description, depends_on keys, ai_assist, validation)
# `when` is the capability that pulls the task in ("*" = always).
TASKS: list[dict] = [
    dict(key="clarify", when="*", phase="Understand", title="Clarify requirements and record assumptions",
         description="Resolve open questions, define acceptance criteria and non-goals with the stakeholder.",
         deps=[], ai="Ask AI to list ambiguities and draft clarifying questions; engineer decides which answers are accepted.",
         validation="Acceptance criteria are written, measurable and signed off."),
    dict(key="design", when="*", phase="Design", title="Design architecture and data/API contracts",
         description="Choose components, data model, API contract and key trade-offs; document decisions.",
         deps=["clarify"], ai="Use AI to compare design options and draft an OpenAPI/schema; engineer selects and justifies.",
         validation="Design review: every requirement maps to a component; trade-offs recorded."),
    dict(key="scaffold", when="*", phase="Build", title="Scaffold project, configuration and tooling",
         description="Project layout, dependency management, config via environment, lint/test tooling.",
         deps=["design"], ai="AI generates boilerplate; engineer prunes unused dependencies and checks versions exist.",
         validation="Clean checkout installs and runs the (empty) test suite."),

    dict(key="persistence", when="persistence", phase="Build", title="Implement persistent storage layer",
         description="Schema, indexes, constraints and data-access code; migrations strategy.",
         deps=["design", "scaffold"], ai="AI drafts models and queries; engineer reviews indexes, constraints and transaction boundaries.",
         validation="Integration tests against a real database; data survives restart."),
    dict(key="core_logic", when="api", phase="Build", title="Implement core domain logic and API endpoints",
         description="Request validation, business rules, error model and endpoint handlers.",
         deps=["design", "scaffold"], ai="AI generates handlers and validators; engineer verifies edge cases and error semantics.",
         validation="Unit tests for rules; API tests for status codes and error bodies."),
    dict(key="auth", when="auth", phase="Build", title="Add authentication and authorisation",
         description="Credential issuing/storage, request authentication, ownership checks.",
         deps=["core_logic"], ai="AI proposes scheme; engineer checks hashing, constant-time compare and IDOR/ownership paths.",
         validation="Negative tests: missing/invalid credentials, cross-tenant access."),
    dict(key="expiry", when="expiry", phase="Build", title="Implement expiration / lifecycle rules",
         description="TTL semantics, status codes for expired/disabled items, clock handling.",
         deps=["core_logic", "persistence"], ai="AI drafts logic; engineer injects a clock to test boundaries deterministically.",
         validation="Boundary tests around the expiry instant, including cached entries."),
    dict(key="bulk", when="bulk", phase="Build", title="Support bulk operations",
         description="Batch endpoint with per-item results and size limits.",
         deps=["core_logic"], ai="AI drafts batch handler; engineer decides atomic vs partial-success semantics.",
         validation="Mixed valid/invalid batch test; max-size enforcement."),
    dict(key="analytics", when="analytics", phase="Build", title="Implement event capture and analytics queries",
         description="Capture events off the hot path, enrich, aggregate by time and dimension.",
         deps=["persistence", "core_logic"], ai="AI drafts aggregation queries; engineer checks time-zone, bucketing and index use.",
         validation="Seeded-data tests with known aggregates; query plan check on large data."),
    dict(key="caching", when="caching", phase="Build", title="Add caching layer",
         description="Cache hot reads with invalidation and TTL; define consistency expectations.",
         deps=["core_logic"], ai="AI suggests cache design; engineer defines invalidation rules and staleness bounds.",
         validation="Tests proving invalidation on update/delete; hit-rate observed."),
    dict(key="rate_limiting", when="rate_limiting", phase="Build", title="Add rate limiting / abuse protection",
         description="Per-identity limits with clear 429 semantics and Retry-After.",
         deps=["core_logic"], ai="AI drafts limiter; engineer reviews memory bounds and per-instance vs shared limits.",
         validation="Burst/refill tests; limiter memory is bounded."),
    dict(key="scalability", when="scalability", phase="Build", title="Address scalability: statelessness, async work, limits",
         description="Keep app stateless, move slow work off the request path, identify bottlenecks.",
         deps=["core_logic", "persistence"], ai="AI proposes bottlenecks and fixes; engineer validates with measurements, not assumptions.",
         validation="Load test with stated target; document measured throughput and limits."),
    dict(key="ui", when="ui", phase="Build", title="Build user interface",
         description="Screens/forms/dashboard for the primary workflow.",
         deps=["core_logic"], ai="AI scaffolds components; engineer checks accessibility and input handling.",
         validation="Manual walkthrough plus component/e2e tests."),

    dict(key="understand_code", when="brownfield", phase="Understand", title="Read existing code and map the affected area",
         description="Locate relevant modules, entry points, data flow and existing tests.",
         deps=["clarify"], ai="Use AI to summarise unfamiliar modules and trace call paths; engineer verifies by reading the code.",
         validation="Short written map of impacted files and invariants."),
    dict(key="characterize", when="brownfield", phase="Test", title="Add characterization tests for current behaviour",
         description="Pin existing behaviour before changing it so regressions are detectable.",
         deps=["understand_code"], ai="AI generates tests from existing behaviour; engineer removes tests that encode bugs.",
         validation="Tests pass on the unmodified code."),
    dict(key="reproduce", when="bugfix", phase="Test", title="Reproduce the defect with a failing test",
         description="Capture the failing scenario in an automated test and find the root cause.",
         deps=["understand_code"], ai="AI helps form hypotheses and minimise the repro; engineer confirms root cause.",
         validation="New test fails before the fix and passes after."),
    dict(key="change", when="brownfield", phase="Build", title="Implement the change with minimal blast radius",
         description="Apply the enhancement/fix/refactor in small reviewable steps.",
         deps=["characterize"], ai="AI proposes diffs; engineer reviews each hunk and rejects unrelated edits.",
         validation="Diff review; all characterization tests still pass."),
    dict(key="refactor", when="refactor", phase="Build", title="Refactor in behaviour-preserving steps",
         description="Restructure code with tests green after every step.",
         deps=["characterize"], ai="AI suggests extractions/renames; engineer keeps behaviour identical.",
         validation="No test changes needed except for moved imports; complexity metrics improved."),
    dict(key="perf_baseline", when="performance", phase="Test", title="Measure baseline and profile hot spots",
         description="Benchmark current behaviour so improvements are evidenced.",
         deps=["clarify"], ai="AI interprets profiler output; engineer decides what is worth optimising.",
         validation="Before/after numbers on the same workload."),

    dict(key="tests", when="*", phase="Test", title="Write unit and integration tests",
         description="Cover rules, error paths, persistence and API contract; include negative and boundary cases.",
         deps=["core_logic"], ai="AI drafts test cases and fixtures; engineer checks they would fail without the feature (no tautologies).",
         validation="Coverage report reviewed for meaningful branches; mutation spot-checks."),
    dict(key="security_review", when="*", phase="Validate", title="Security and performance review",
         description="Input validation, injection/SSRF/open-redirect, secrets handling, resource exhaustion, N+1 queries.",
         deps=["tests"], ai="AI acts as reviewer producing a checklist; engineer triages and fixes findings.",
         validation="Checklist items closed or explicitly accepted as risks."),
    dict(key="docs", when="*", phase="Document", title="Write documentation and API reference",
         description="Setup, usage, architecture/trade-offs, known limitations.",
         deps=["tests"], ai="AI drafts docs from code; engineer verifies every command and example actually runs.",
         validation="A new reader can run and evaluate the solution from the README alone."),
    dict(key="summary", when="*", phase="Document", title="Produce final engineering summary",
         description="Approach, artifacts, risks, validation results, assumptions and limitations.",
         deps=["docs", "security_review"], ai="AI structures the summary; engineer owns every claim and its evidence.",
         validation="Each claim links to a test, measurement or code reference."),
]

AI_RISKS = [
    dict(category="ai", risk="AI-generated code may contain hallucinated APIs, wrong library versions or subtle logic errors.",
         impact="Runtime failures or incorrect behaviour that looks plausible.",
         mitigation="Run everything; review each hunk; pin dependency versions; prefer small iterative prompts."),
    dict(category="ai", risk="AI-generated tests can be shallow, tautological or mirror the implementation (coverage gaps).",
         impact="False confidence; defects escape.",
         mitigation="Require negative/boundary cases, confirm tests fail without the change, review coverage by branch."),
    dict(category="ai", risk="AI tends to over-engineer or pick inefficient patterns (N+1 queries, blocking I/O on hot paths).",
         impact="Unnecessary complexity or poor performance.",
         mitigation="Set explicit non-functional targets, profile/measure, simplify before accepting."),
    dict(category="ai", risk="AI may suggest insecure defaults (hard-coded secrets, permissive validation).",
         impact="Vulnerabilities shipped unnoticed.",
         mitigation="Security checklist review, secrets via environment, adversarial tests for inputs."),
]

CAPABILITY_RISKS: dict[str, list[dict]] = {
    "persistence": [
        dict(category="design", risk="Schema/index choices may not suit query patterns as data grows.",
             impact="Slow queries, painful migrations.", mitigation="Model access patterns first; index for them; plan migrations (Alembic)."),
        dict(category="functional", risk="Concurrent writes can create duplicates or lose updates.",
             impact="Data integrity issues.", mitigation="Use DB constraints and transactions; test concurrent paths."),
    ],
    "analytics": [
        dict(category="design", risk="Writing analytics synchronously on the request path adds latency and couples availability.",
             impact="Slow user-facing requests.", mitigation="Queue events and batch-write; accept bounded loss or use a durable broker."),
        dict(category="functional", risk="Privacy: raw IPs/user agents are personal data.",
             impact="Compliance exposure.", mitigation="Hash/minimise identifiers, define retention, document."),
    ],
    "caching": [
        dict(category="design", risk="Stale cache after updates, especially across multiple instances.",
             impact="Disabled/changed items keep being served.", mitigation="Invalidate on write, bound TTL, use shared cache when scaling out."),
    ],
    "scalability": [
        dict(category="design", risk="Scalability target is unquantified so the design may be over- or under-built.",
             impact="Wasted effort or outage under load.", mitigation="Agree numeric targets; load-test; document measured limits."),
    ],
    "auth": [
        dict(category="functional", risk="Broken access control (users reading/modifying others' data).",
             impact="Data exposure.", mitigation="Ownership check on every resource lookup; return 404 for foreign resources; tests."),
    ],
    "rate_limiting": [
        dict(category="design", risk="Per-process limiters are not global in multi-instance deployments.",
             impact="Effective limit is N times higher.", mitigation="Shared store (Redis) or edge limiting when scaling out."),
    ],
    "expiry": [
        dict(category="functional", risk="Time/clock edge cases (UTC, boundaries, caching beyond expiry).",
             impact="Links served after expiry or expired early.", mitigation="UTC everywhere, injectable clock, boundary tests."),
    ],
    "bugfix": [
        dict(category="functional", risk="Fix addresses a symptom, not the root cause, or breaks adjacent behaviour.",
             impact="Recurring or new defects.", mitigation="Failing test first; characterization tests around neighbours."),
    ],
    "refactor": [
        dict(category="functional", risk="Behaviour changes sneak in during restructuring.",
             impact="Regressions.", mitigation="Pin behaviour with tests; refactor in small green steps."),
    ],
    "performance": [
        dict(category="design", risk="Optimising without a baseline can target the wrong thing.",
             impact="Complexity with no gain.", mitigation="Measure before/after on a representative workload."),
    ],
}
