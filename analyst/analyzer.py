"""Deterministic, rule-based requirement analyser.

Turns a free-text requirement into: classification (greenfield / brownfield /
ambiguous), ambiguities with clarifying questions, explicit assumptions, an
engineering problem statement, a dependency-ordered task breakdown with the AI
assist and validation for each task, risks with mitigations and trade-offs.

It is intentionally not an LLM: output is reproducible and reviewable. An LLM
can be layered on top for prose, but the engineer owns the rules in catalog.py.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from analyst import catalog

AMBIGUITY_THRESHOLD = 3

TRADEOFFS = {
    "persistence": "SQLite is zero-setup but single-writer; PostgreSQL scales better at the cost of operating a server.",
    "analytics": "Asynchronous event capture keeps the hot path fast but can lose in-flight events on a crash; durable queues cost complexity.",
    "caching": "Caching cuts latency and DB load but introduces staleness; shorter TTL = fresher data, lower hit rate.",
    "scalability": "Stateless instances scale horizontally, but per-process caches/limiters then need shared backends.",
    "rate_limiting": "Strict limits protect the service but can reject legitimate bursts; token buckets trade precision for burst tolerance.",
    "expiry": "Soft-deleting/retaining expired data enables audit and analytics but consumes storage.",
    "auth": "API keys are simple and stateless to verify; OAuth/JWT offer delegation at higher implementation cost.",
    "bulk": "Partial-success batches are friendlier to clients than all-or-nothing but need per-item error reporting.",
    "refactor": "Smaller refactor steps are safer but slower to land.",
}

DEFAULT_ASSUMPTIONS = {
    "api": "Interface is a JSON/REST HTTP API with an OpenAPI contract.",
    "persistence": "A relational database is acceptable; schema evolves via migrations.",
    "analytics": "Analytics are near-real-time (seconds), aggregated per link, and identifiers are hashed for privacy.",
    "auth": "Callers authenticate with API keys; public read paths (e.g. redirects) are unauthenticated.",
    "caching": "Slightly stale reads (bounded TTL) are acceptable; writes invalidate the cache.",
    "scalability": "Horizontal scaling of stateless instances behind a load balancer; numeric targets are to be confirmed.",
    "rate_limiting": "Limits are per API key (authenticated) or per IP (anonymous).",
    "expiry": "Times are UTC; expired links answer 410 Gone.",
}


@dataclass
class Analysis:
    requirement: str
    classification: dict
    engineering_problem: str
    capabilities: list[str]
    ambiguities: list[dict]
    assumptions: list[str]
    tasks: list[dict]
    execution_order: list[str]
    parallel_waves: list[list[str]]
    risks: list[dict]
    tradeoffs: list[str]
    validation_plan: list[str]
    needs_clarification: bool
    context: dict | None = None

    def to_dict(self) -> dict:
        """Return a shallow copy of the analysis fields as a dict."""
        return self.__dict__.copy()


def _matches(text: str, keyword: str, prefix: bool) -> bool:
    """Return True if the keyword occurs at a word start, as a stem or as a whole word with s/es."""
    kw = re.escape(keyword)
    pattern = rf"\b{kw}" if prefix else rf"\b{kw}(?:s|es)?\b"
    return re.search(pattern, text) is not None


def _kw_hit(text: str, keyword: str) -> bool:
    """Return True if the keyword matches the text, treating long keywords as stems."""
    # short keywords ("ui", "api", "fix") must match whole words, longer ones are stems
    return _matches(text, keyword, prefix=len(keyword) > 4)


def detect_capabilities(text: str) -> list[str]:
    """Return the catalog capabilities whose keywords appear in the text."""
    return [cap for cap, kws in catalog.CAPABILITIES.items() if any(_kw_hit(text, k) for k in kws)]


def scan_context(path: str, requirement: str, max_files: int = 2000) -> dict:
    """Cheap brownfield context: languages, test presence, frameworks, files related to the requirement."""
    skip = {".git", ".venv", "venv", "node_modules", "__pycache__", ".idea", ".vscode", "dist", "build"}
    languages: dict[str, int] = {}
    files: list[str] = []
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in names:
            files.append(os.path.join(root, name))
            ext = os.path.splitext(name)[1].lower()
            if ext in {".py", ".js", ".ts", ".java", ".go", ".cs", ".rb", ".rs"}:
                languages[ext] = languages.get(ext, 0) + 1
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break

    frameworks = set()
    for f in files:
        base = os.path.basename(f).lower()
        if base in {"requirements.txt", "pyproject.toml", "package.json", "pom.xml", "go.mod"}:
            try:
                content = open(f, encoding="utf-8", errors="ignore").read().lower()
            except OSError:
                continue
            for fw in ("fastapi", "flask", "django", "express", "spring", "sqlalchemy", "pytest", "jest"):
                if fw in content:
                    frameworks.add(fw)

    words = {w for w in re.findall(r"[a-z]{4,}", requirement.lower()) if w not in {"that", "with", "this", "from", "should"}}
    scored = []
    for f in files:
        if not f.endswith((".py", ".js", ".ts", ".java", ".go")):
            continue
        try:
            content = open(f, encoding="utf-8", errors="ignore").read(40_000).lower()
        except OSError:
            continue
        score = sum(content.count(w) for w in words) + 5 * sum(w in os.path.basename(f).lower() for w in words)
        if score:
            scored.append((score, os.path.relpath(f, path)))
    scored.sort(reverse=True)
    return {
        "path": path,
        "files_scanned": len(files),
        "languages": languages,
        "frameworks": sorted(frameworks),
        "has_tests": any("test" in os.path.basename(f).lower() for f in files),
        "likely_relevant_files": [p for _, p in scored[:8]],
    }


def _find_ambiguities(text: str, caps: list[str], is_brownfield: bool, has_context: bool) -> list[dict]:
    """Return weighted ambiguities, each with a clarifying question and default assumption."""
    found: list[dict] = []
    words = re.findall(r"[a-z0-9\-']+", text)

    for term, question in catalog.VAGUE_TERMS.items():
        if re.search(rf"\b{re.escape(term)}", text):
            found.append(dict(topic=f"vague term: '{term}'", weight=1,
                              issue=f"'{term}' is not testable as written.", clarifying_question=question,
                              default_assumption="Pick a conservative measurable target and confirm it."))
    if len(words) < 6:
        found.append(dict(topic="insufficient detail", weight=2,
                          issue="The requirement is too short to derive scope.",
                          clarifying_question="Who is the user, what outcome do they need, and what is out of scope?",
                          default_assumption="None - blocked until clarified."))
    if not caps:
        found.append(dict(topic="no recognisable capability", weight=3,
                          issue="No concrete capability (API, storage, bug, refactor...) could be identified.",
                          clarifying_question="What should the system do, or what is wrong with the current behaviour?",
                          default_assumption="None - blocked until clarified."))
    if "scalability" in caps and not any(h in text for h in catalog.SCALE_HINT) and not re.search(r"\d", text):
        found.append(dict(topic="scale target", weight=1,
                          issue="Scalability is requested without numbers.",
                          clarifying_question="Expected peak requests/sec, total records, read:write ratio, growth rate?",
                          default_assumption="Design for ~1k redirects/sec per instance and horizontal scale-out."))
    if "persistence" in caps and not re.search(r"postgres|mysql|sqlite|mongo|dynamo|oracle|sql server", text):
        found.append(dict(topic="datastore choice", weight=0,
                          issue="No datastore specified.",
                          clarifying_question="Is there a mandated database, or operational constraints (managed service, no Docker)?",
                          default_assumption="SQLite for the prototype behind an ORM, PostgreSQL for production."))
    if "analytics" in caps:
        found.append(dict(topic="analytics scope", weight=0,
                          issue="'Analytics' can mean totals, time series, or segmentation.",
                          clarifying_question="Which dimensions (time, referrer, device, geo, unique visitors), freshness and retention?",
                          default_assumption="Totals, time series, referrer, device/browser/OS, country, unique visitors."))
    if "auth" in caps:
        found.append(dict(topic="identity model", weight=0,
                          issue="Callers and trust boundaries are not defined.",
                          clarifying_question="Who are the callers and is multi-tenancy needed?",
                          default_assumption="API keys identify tenants; links are private to their creator."))
    if "bugfix" in caps and not re.search(r"expect|should|steps|reproduc|instead|when ", text):
        found.append(dict(topic="defect description", weight=1,
                          issue="Expected vs actual behaviour or reproduction steps are missing.",
                          clarifying_question="What is the exact input, actual output and expected output?",
                          default_assumption="Assume the documented behaviour is the expected one."))
    if is_brownfield and not has_context:
        found.append(dict(topic="existing system context", weight=1,
                          issue="Brownfield work needs the affected code, versions and conventions.",
                          clarifying_question="Which module/service is affected, and can the repo be provided (--context-dir)?",
                          default_assumption="Follow the conventions of the surrounding code once inspected."))
    return found


def _classify(text: str, caps: list[str], ambiguity_score: int, has_context: bool) -> dict:
    """Classify the requirement as greenfield, brownfield or ambiguous with signals and confidence."""
    gf = [s for s in catalog.GREENFIELD_SIGNALS if s in text]
    bf = [s for s in catalog.BROWNFIELD_SIGNALS if s in text]
    if any(c in caps for c in ("bugfix", "refactor")):
        bf.append("capability:bugfix/refactor")
    if has_context and not gf:
        bf.append("context-dir provided")
    likely = "brownfield" if len(bf) > len(gf) else "greenfield"
    total = len(gf) + len(bf)
    confidence = round(max(len(gf), len(bf)) / total, 2) if total else 0.0
    kind = "ambiguous" if ambiguity_score >= AMBIGUITY_THRESHOLD else likely
    return {
        "type": kind,
        "likely_type": likely,
        "confidence": confidence,
        "ambiguity_score": ambiguity_score,
        "signals": {"greenfield": gf, "brownfield": bf},
    }


def _order(tasks: list[dict]) -> tuple[list[str], list[list[str]]]:
    """Topologically sort tasks into an execution order and parallel waves, raising on cycles."""
    index = {t["id"]: i for i, t in enumerate(tasks)}
    done: set[str] = set()
    order: list[str] = []
    waves: list[list[str]] = []
    remaining = [t["id"] for t in tasks]
    deps = {t["id"]: set(t["depends_on"]) for t in tasks}
    while remaining:
        ready = sorted((t for t in remaining if deps[t] <= done), key=index.get)
        if not ready:
            raise ValueError(f"dependency cycle among {remaining}")
        waves.append(ready)
        order.extend(ready)
        done.update(ready)
        remaining = [t for t in remaining if t not in done]
    return order, waves


def _build_tasks(caps: list[str], kind: str) -> list[dict]:
    """Select and wire catalog tasks and their dependencies for the capabilities and project kind."""
    brownfield = kind == "brownfield"
    active = set(caps)
    if brownfield:
        active.add("brownfield")
    selected = []
    for t in catalog.TASKS:
        if t["key"] == "scaffold" and brownfield:
            continue  # existing project already has scaffolding
        if t["when"] == "*" or t["when"] in active:
            selected.append(t)
    keys = {t["key"] for t in selected}
    build_keys = [t["key"] for t in selected if t["phase"] == "Build"]
    tasks = []
    for n, t in enumerate(selected, 1):
        deps = [d for d in t["deps"] if d in keys]
        if t["key"] == "tests":
            deps = [k for k in build_keys] or ["clarify"]
        if brownfield and t["phase"] == "Build" and "characterize" in keys and "characterize" not in deps:
            deps.append("characterize")
        if brownfield and t["key"] == "design" and "understand_code" in keys:
            deps.append("understand_code")
        tasks.append(dict(id=t["key"], seq=n, phase=t["phase"], title=t["title"], description=t["description"],
                          depends_on=list(dict.fromkeys(deps)), ai_assist=t["ai"], validation=t["validation"]))
    return tasks


def _problem_statement(requirement: str, kind: str, caps: list[str], ambiguities: list[dict]) -> str:
    """Compose the engineering problem statement from the requirement, scope and blocking questions."""
    scope = ", ".join(c.replace("_", " ") for c in caps) or "unspecified"
    mode = {"greenfield": "Design and build a new system", "brownfield": "Change an existing system",
            "ambiguous": "Clarify, then deliver"}[kind]
    blocking = [a["topic"] for a in ambiguities if a["weight"] > 0]
    tail = f" Open questions to settle first: {', '.join(blocking)}." if blocking else ""
    return f"{mode} to satisfy: \"{requirement.strip()}\" Scope capabilities: {scope}.{tail}"


def analyze(requirement: str, context_dir: str | None = None) -> Analysis:
    """Analyse a requirement into an Analysis; raise ValueError if it is empty."""
    requirement = " ".join(requirement.split())
    if not requirement:
        raise ValueError("requirement must not be empty")
    text = requirement.lower()
    caps = detect_capabilities(text)
    context = scan_context(context_dir, requirement) if context_dir else None

    provisional = _classify(text, caps, 0, context is not None)
    ambiguities = _find_ambiguities(text, caps, provisional["likely_type"] == "brownfield", context is not None)
    score = sum(a["weight"] for a in ambiguities)
    classification = _classify(text, caps, score, context is not None)
    kind = classification["type"]
    effective = classification["likely_type"] if kind == "ambiguous" else kind

    tasks = _build_tasks(caps, effective)
    if kind == "ambiguous":
        for t in tasks:
            if t["id"] == "clarify":
                t["description"] += " BLOCKING: the requirement is ambiguous; do not start build tasks until answered."
    order, waves = _order(tasks)
    by_id = {t["id"]: t for t in tasks}
    tasks = [by_id[i] for i in order]
    for n, t in enumerate(tasks, 1):
        t["seq"] = n

    assumptions = [DEFAULT_ASSUMPTIONS[c] for c in caps if c in DEFAULT_ASSUMPTIONS]
    assumptions += [a["default_assumption"] for a in ambiguities if not a["default_assumption"].startswith("None")]
    assumptions.append("Engineer reviews and owns all AI-generated output; nothing is accepted without running it.")
    assumptions = list(dict.fromkeys(assumptions))

    risks = []
    if kind == "ambiguous" or score:
        risks.append(dict(category="functional", risk="Ambiguous requirement leads to building the wrong thing.",
                          impact="Rework and missed expectations.",
                          mitigation="Resolve blocking questions first; record assumptions; demo early."))
    for c in caps:
        risks.extend(catalog.CAPABILITY_RISKS.get(c, []))
    risks.extend(catalog.AI_RISKS)

    validation = list(dict.fromkeys(t["validation"] for t in tasks))
    validation.append("All AI-generated code reviewed line by line and executed before acceptance.")

    return Analysis(
        requirement=requirement,
        classification=classification,
        engineering_problem=_problem_statement(requirement, kind, caps, ambiguities),
        capabilities=caps,
        ambiguities=ambiguities,
        assumptions=assumptions,
        tasks=tasks,
        execution_order=order,
        parallel_waves=waves,
        risks=risks,
        tradeoffs=[TRADEOFFS[c] for c in caps if c in TRADEOFFS],
        validation_plan=validation,
        needs_clarification=kind == "ambiguous",
        context=context,
    )


def to_markdown(a: Analysis) -> str:
    """Render an Analysis as a Markdown report."""
    c = a.classification
    out = [
        "# Requirement Analysis", "",
        f"> {a.requirement}", "",
        f"**Classification:** {c['type']} (likely {c['likely_type']}, confidence {c['confidence']}, ambiguity score {c['ambiguity_score']})  ",
        f"**Needs clarification before build:** {'yes' if a.needs_clarification else 'no'}  ",
        f"**Capabilities:** {', '.join(a.capabilities) or 'none detected'}", "",
        "## Engineering problem", a.engineering_problem, "",
    ]
    if a.context:
        ctx = a.context
        out += ["## Existing code context", f"- Files scanned: {ctx['files_scanned']}; languages: {ctx['languages']}",
                f"- Frameworks: {', '.join(ctx['frameworks']) or 'n/a'}; tests present: {ctx['has_tests']}",
                f"- Likely relevant files: {', '.join(ctx['likely_relevant_files']) or 'none found'}", ""]
    out += ["## Ambiguities and clarifying questions"]
    out += [f"- **{x['topic']}** - {x['issue']} _Q: {x['clarifying_question']}_ (default: {x['default_assumption']})"
            for x in a.ambiguities] or ["- None detected"]
    out += ["", "## Assumptions"] + [f"- {x}" for x in a.assumptions]
    out += ["", "## Task breakdown (engineer-led, AI-assisted)", "",
            "| # | Task | Phase | Depends on | AI assists with | Validation |", "|---|---|---|---|---|---|"]
    for t in a.tasks:
        out.append(f"| {t['seq']} | **{t['title']}**<br>{t['description']} | {t['phase']} | {', '.join(t['depends_on']) or '-'} | {t['ai_assist']} | {t['validation']} |")
    out += ["", "## Execution sequence", ""]
    out += [f"{i}. Wave {i}: {', '.join(w)}" for i, w in enumerate(a.parallel_waves, 1)]
    out += ["", "## Risks and mitigations", "", "| Category | Risk | Impact | Mitigation |", "|---|---|---|---|"]
    out += [f"| {r['category']} | {r['risk']} | {r['impact']} | {r['mitigation']} |" for r in a.risks]
    out += ["", "## Trade-offs"] + [f"- {t}" for t in a.tradeoffs]
    out += ["", "## Validation plan"] + [f"- {v}" for v in a.validation_plan]
    return "\n".join(out) + "\n"
