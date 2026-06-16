# qa_engine Core (Phase 1a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the tested `inconsistency_resolver` package into a universal, UI-agnostic `qa_engine` that reads any memoQ mqxliff's embedded QA codes and produces a `ReviewSession` (auto-applied fixes + items needing human approval), then applies approved decisions to a corrected mqxliff — driven by a per-code resolver registry with an injectable AI client.

**Architecture:** A registry maps each memoQ QA code to a Resolver (`deterministic` / `ai` / `report_only`). `engine.analyze(bytes) → ReviewSession` parses the embedded `<mq:errorwarning>` issues, routes each to its resolver, and splits results into auto-applied / pending-approval / report-only. `engine.apply(bytes, decisions) → fixed bytes` writes the chosen fixes with the existing format-preserving, XML-validated writer. No UI imports; the AI client is injected via an `AIClient` protocol so a standalone Claude adapter or AnovaAITool's `AITranslator` can both drive it.

**Tech Stack:** Python 3.11+, `anthropic` SDK (Claude Opus 4.8, injectable), `lxml`, `pytest`. Builds on the existing tested core (parser, tags, whitespace, apply — 46 tests).

**Scope note:** This plan delivers the engine core only. The standalone FastAPI web UI (Phase 1b) is a separate plan that consumes `engine.analyze` / `engine.apply`. Additional AI resolvers (terminology, punctuation, numbers) and AnovaAITool integration are Phases 2–3.

---

### Task 1: Rename package `inconsistency_resolver` → `qa_engine`

Intra-package imports are relative (`from .models`), so only test files, `cli.py`, and `__main__.py` reference the package name.

**Files:**
- Rename: `inconsistency_resolver/` → `qa_engine/`
- Modify: all `tests/test_*.py`, `qa_engine/cli.py`, `qa_engine/__main__.py`

- [ ] **Step 1: Rename the package directory (preserve history)**

Run:
```bash
cd "C:/Users/ada/Documents/Claude/Projects/QA resolvers/Inconsistency"
git mv inconsistency_resolver qa_engine
```

- [ ] **Step 2: Update all external references**

Run (PowerShell-safe via python):
```bash
python - <<'PY'
import pathlib, re
for p in list(pathlib.Path("tests").glob("test_*.py")) + [pathlib.Path("qa_engine/cli.py"), pathlib.Path("qa_engine/__main__.py")]:
    t = p.read_text(encoding="utf-8")
    t2 = t.replace("inconsistency_resolver", "qa_engine")
    if t2 != t:
        p.write_text(t2, encoding="utf-8")
        print("updated", p)
PY
```

- [ ] **Step 3: Run the full suite to confirm the rename is clean**

Run: `python -m pytest -q`
Expected: all 46 tests pass (no `ModuleNotFoundError`).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename package inconsistency_resolver -> qa_engine"
```
End the commit message with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 2: Issue / Resolution / ResolvedItem / ReviewSession models

**Files:**
- Modify: `qa_engine/models.py`
- Test: `tests/test_engine_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_engine_models.py`:
```python
from qa_engine.models import Issue, Resolution, ResolvedItem, ReviewSession


def test_issue_fields():
    i = Issue(code="3050", problemname="multiple consecutive whitespaces",
              args="x", segmentguid="g1", tu_id="1")
    assert i.code == "3050" and i.segmentguid == "g1"


def test_resolution_defaults():
    r = Resolution(action="report")
    assert r.new_target is None and r.confidence == 0.0
    assert r.needs_approval is True and r.strategy == ""


def test_resolved_item_holds_resolution():
    r = Resolution(action="fix", new_target="X", confidence=1.0,
                   needs_approval=False, strategy="deterministic")
    it = ResolvedItem(item_id="g1:3050:0", segmentguid="g1", tu_id="1",
                      code="3050", problemname="p", source_preview="s",
                      current_target_preview="t", proposed_target_preview="X",
                      resolution=r)
    assert it.resolution.action == "fix" and it.item_id == "g1:3050:0"


def test_review_session_buckets():
    rs = ReviewSession(source_lang="en", target_lang="el",
                       auto_applied=[], pending=[], report_only=[])
    assert rs.source_lang == "en" and rs.auto_applied == []
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_engine_models.py -v`
Expected: FAIL `ImportError` (names not defined).

- [ ] **Step 3: Add the models to `qa_engine/models.py`** (append, keep existing `Member`/`Case`/`Decision`)

```python
@dataclass
class Issue:
    code: str
    problemname: str
    args: str
    segmentguid: str
    tu_id: str


@dataclass
class Resolution:
    action: str                       # "fix" | "ignore" | "report"
    new_target: Optional[str] = None  # write-ready raw inner XML when action == "fix"
    confidence: float = 0.0
    needs_approval: bool = True
    rationale: str = ""
    strategy: str = ""                # "deterministic" | "ai" | "report_only"


@dataclass
class ResolvedItem:
    item_id: str                      # f"{segmentguid}:{code}:{index}"
    segmentguid: str
    tu_id: str
    code: str
    problemname: str
    source_preview: str
    current_target_preview: str
    proposed_target_preview: Optional[str]
    resolution: Resolution


@dataclass
class ReviewSession:
    source_lang: str
    target_lang: str
    auto_applied: list                # list[ResolvedItem]  (apply without asking)
    pending: list                     # list[ResolvedItem]  (need human approval)
    report_only: list                 # list[ResolvedItem]  (informational)
```

- [ ] **Step 4: Run; verify pass; run full suite**

Run: `python -m pytest tests/test_engine_models.py -v` → PASS (4). Then `python -m pytest -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add qa_engine/models.py tests/test_engine_models.py
git commit -m "feat: add Issue/Resolution/ResolvedItem/ReviewSession models"
```

---

### Task 3: Parse embedded issues + segment lookup

Add a parser that returns the `Issue` list and a `segmentguid → Member` map, plus the file's source/target language. Reuses the existing `parse_mqxliff`.

**Files:**
- Modify: `qa_engine/parser.py`
- Test: `tests/test_parse_issues.py`

- [ ] **Step 1: Write the failing test** (uses the existing `tests/fixtures/sample.mqxliff`)

`tests/test_parse_issues.py`:
```python
from pathlib import Path
from qa_engine.parser import parse_issues, parse_languages

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_parse_languages():
    src, tgt = parse_languages(FIX.read_bytes())
    assert src == "en" and tgt == "el"


def test_parse_issues_returns_issue_per_warning():
    issues, members = parse_issues(FIX.read_bytes())
    # fixture has 5 inconsistency warnings (tu1-5) -> 5 issues
    assert len(issues) == 5
    codes = {i.code for i in issues}
    assert "03101" in codes or "3101" in codes
    # members keyed by segmentguid
    assert "g1" in members and members["g1"].tu_id == "1"


def test_issue_has_segment_link():
    issues, members = parse_issues(FIX.read_bytes())
    i = issues[0]
    assert i.segmentguid in members
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_parse_issues.py -v`
Expected: FAIL `ImportError`.

- [ ] **Step 3: Implement in `qa_engine/parser.py`** (append; the file already imports `etree`, `Member`, `tokenize`)

```python
from .models import Issue   # add to existing imports at top


def parse_languages(content: bytes):
    root = etree.fromstring(content)
    f = root.find(f"{{{_XLIFF}}}file")
    if f is None:
        return None, None
    return f.get("source-language"), f.get("target-language")


def parse_issues(content: bytes):
    """Return (issues, members_by_guid). One Issue per <mq:errorwarning>."""
    import tempfile, os
    # parse_mqxliff takes a path; write bytes to a temp file
    fd, path = tempfile.mkstemp(suffix=".mqxliff")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        members = parse_mqxliff(path)
    finally:
        os.unlink(path)
    by_guid = {m.segmentguid: m for m in members}

    root = etree.fromstring(content)
    issues = []
    for tu in root.iter(f"{{{_XLIFF}}}trans-unit"):
        guid = tu.get(f"{{{_MQ}}}segmentguid")
        tu_id = tu.get("id")
        for ew in tu.iter(f"{{{_MQ}}}errorwarning"):
            issues.append(Issue(
                code=ew.get(f"{{{_MQ}}}errorwarning-code", ""),
                problemname=ew.get(f"{{{_MQ}}}errorwarning-problemname", ""),
                args=ew.get(f"{{{_MQ}}}errorwarning-localizationargs", ""),
                segmentguid=guid, tu_id=tu_id,
            ))
    return issues, by_guid
```

- [ ] **Step 4: Run; verify pass; full suite**

Run: `python -m pytest tests/test_parse_issues.py -v` → PASS (3). Then `python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add qa_engine/parser.py tests/test_parse_issues.py
git commit -m "feat: parse embedded QA issues and segment/language metadata"
```

---

### Task 4: AIClient protocol + Claude adapter; refactor classify_case to use it

Decouple the AI from the raw Anthropic SDK shape so any provider (standalone Claude, AnovaAITool `AITranslator`) can be injected.

**Files:**
- Create: `qa_engine/aiclient.py`
- Modify: `qa_engine/ai.py`
- Test: `tests/test_aiclient.py`
- Modify: `tests/test_ai.py` (fake now implements `AIClient.resolve`)

- [ ] **Step 1: Write the failing test**

`tests/test_aiclient.py`:
```python
import json
from qa_engine.aiclient import ClaudeAIClient


class _FakeAnthropic:
    class messages:
        last = {}
        @staticmethod
        def create(**kw):
            _FakeAnthropic.messages.last = kw
            return type("M", (), {"content": [type("B", (), {"type": "text",
                        "text": json.dumps({"ok": True})})()]})()


def test_claude_client_resolve_builds_request_and_parses():
    c = ClaudeAIClient(anthropic_client=_FakeAnthropic(), model="claude-opus-4-8")
    out = c.resolve("sys", "user", {"type": "object"})
    assert out == {"ok": True}
    kw = _FakeAnthropic.messages.last
    assert kw["model"] == "claude-opus-4-8"
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["format"]["schema"] == {"type": "object"}
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_aiclient.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `qa_engine/aiclient.py`**

```python
import json
from typing import Protocol


class AIClient(Protocol):
    def resolve(self, system_prompt: str, user_content: str, schema: dict) -> dict:
        """Run a structured completion and return the parsed JSON object."""
        ...


class ClaudeAIClient:
    """Standalone Claude Opus 4.8 adapter."""

    def __init__(self, anthropic_client=None, model: str = "claude-opus-4-8"):
        if anthropic_client is None:
            import anthropic
            anthropic_client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
        self._c = anthropic_client
        self.model = model

    def resolve(self, system_prompt: str, user_content: str, schema: dict) -> dict:
        resp = self._c.messages.create(
            model=self.model,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user_content}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
```

- [ ] **Step 4: Refactor `qa_engine/ai.py` `classify_case` to use `AIClient`**

Replace the body of `classify_case(client, payload, system_prompt, model)` so it calls `client.resolve(...)` instead of `client.messages.create(...)`. New version:
```python
def classify_case(client, payload: dict, system_prompt: str, model: str) -> Decision:
    user_content = "Resolve this inconsistency case:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    data = client.resolve(system_prompt, user_content, DECISION_SCHEMA)

    chosen_member_id = None
    if data["category"] == "pick_best" and data.get("chosen_variant_key"):
        chosen_member_id = _member_for_target(payload, data["chosen_variant_key"])

    return Decision(
        case_id=payload["case_id"],
        category=data["category"],
        rationale=data["rationale"],
        confidence=data["confidence"],
        chosen_member_id=chosen_member_id,
        differentiated=data.get("differentiated", []),
    )
```
(The `model` param is now unused by `classify_case` itself — the model lives on the client. Keep the parameter in the signature for backward-compatible call sites, but it is ignored. Note: `confidence` in DECISION_SCHEMA is the string `"high"/"medium"/"low"` — keep that; downstream maps it to a float in Task 7.)

- [ ] **Step 5: Update `tests/test_ai.py`** — the `FakeClient` must now expose `.resolve(system_prompt, user_content, schema)` returning the canned dict (instead of `.messages.create`). Replace the fake:
```python
class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.last = None
    def resolve(self, system_prompt, user_content, schema):
        self.last = {"system": system_prompt, "user": user_content, "schema": schema}
        return self._payload
```
And update the assertions that previously inspected `messages.create` kwargs to inspect `fake.last` (`schema == DECISION_SCHEMA`, `"inconsistency" in user.lower()` etc.). Keep `test_system_prompt_includes_categories_and_glossary` unchanged.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_aiclient.py tests/test_ai.py -v` → all pass. Then `python -m pytest -q` → all green.

- [ ] **Step 7: Commit**

```bash
git add qa_engine/aiclient.py qa_engine/ai.py tests/test_aiclient.py tests/test_ai.py
git commit -m "feat: AIClient protocol + Claude adapter; classify_case uses injected client"
```

---

### Task 5: Resolver base, report_only resolver, and registry

**Files:**
- Create: `qa_engine/resolvers/__init__.py`
- Create: `qa_engine/resolvers/base.py`
- Create: `qa_engine/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

`tests/test_registry.py`:
```python
from qa_engine.models import Issue
from qa_engine.registry import get_resolver, STRATEGY_BY_CODE
from qa_engine.resolvers.base import ReportOnlyResolver


def _issue(code):
    return Issue(code=code, problemname="p", args="", segmentguid="g1", tu_id="1")


def test_unknown_code_falls_back_to_report_only():
    r = get_resolver(_issue("99999"))
    assert isinstance(r, ReportOnlyResolver)


def test_known_codes_have_strategies():
    # normalized lookup: both "3050" and "03050" resolve
    assert STRATEGY_BY_CODE["3050"] == "deterministic"
    assert STRATEGY_BY_CODE["3101"] == "ai"
    assert STRATEGY_BY_CODE["3161"] == "report_only"


def test_report_only_resolver_returns_report_action():
    r = ReportOnlyResolver()
    res = r.resolve(_issue("3161"), member=None, context=None)
    assert res.action == "report" and res.strategy == "report_only"
    assert res.needs_approval is True
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_registry.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `qa_engine/resolvers/base.py`**

```python
from ..models import Resolution


def normalize_code(code: str) -> str:
    """memoQ codes appear as zero-padded ('03050'); normalize to plain int string."""
    try:
        return str(int(code))
    except (TypeError, ValueError):
        return code or ""


class Resolver:
    strategy = "report_only"

    def resolve(self, issue, member, context) -> Resolution:
        raise NotImplementedError


class ReportOnlyResolver(Resolver):
    strategy = "report_only"

    def resolve(self, issue, member, context) -> Resolution:
        return Resolution(
            action="report",
            new_target=None,
            confidence=0.0,
            needs_approval=True,
            rationale=f"Code {normalize_code(issue.code)} ({issue.problemname}) "
                      f"is not auto-resolvable; left for human review.",
            strategy="report_only",
        )
```

`qa_engine/resolvers/__init__.py`:
```python
```

- [ ] **Step 4: Implement `qa_engine/registry.py`**

```python
from .resolvers.base import ReportOnlyResolver, normalize_code

# Code -> strategy label. Resolvers are attached in Task 6/7; until then a code
# mapped to deterministic/ai with no registered resolver falls back to report_only.
STRATEGY_BY_CODE = {
    # deterministic whitespace family
    "3050": "deterministic", "3071": "deterministic", "3072": "deterministic",
    "3073": "deterministic", "3074": "deterministic", "3075": "deterministic",
    "3076": "deterministic", "3110": "deterministic", "3190": "deterministic",
    "3191": "deterministic", "3192": "deterministic", "3193": "deterministic",
    "3194": "deterministic", "3195": "deterministic", "3196": "deterministic",
    "3197": "deterministic", "3065": "deterministic", "3069": "deterministic",
    # ai
    "3100": "ai", "3101": "ai",
    # report_only (Phase 1a leaves these for humans)
    "3161": "report_only", "3162": "report_only", "3081": "report_only",
    "3082": "report_only", "3083": "report_only", "3084": "report_only",
}

# Resolver instances are registered here by the engine bootstrap (Task 8).
_RESOLVERS = {}


def register_resolver(code: str, resolver):
    _RESOLVERS[normalize_code(code)] = resolver


def get_resolver(issue):
    return _RESOLVERS.get(normalize_code(issue.code), ReportOnlyResolver())
```

- [ ] **Step 5: Run; verify pass; full suite**

Run: `python -m pytest tests/test_registry.py -v` → PASS (3). Then `python -m pytest -q` → green.

- [ ] **Step 6: Commit**

```bash
git add qa_engine/resolvers tests/test_registry.py qa_engine/registry.py
git commit -m "feat: resolver base, report-only resolver, and code->strategy registry"
```

---

### Task 6: Deterministic whitespace resolver

Wraps the existing, tested `whitespace.align_whitespace` to resolve the whitespace-family codes per segment, producing an auto-applicable `Resolution` (zero-error, no AI).

**Files:**
- Create: `qa_engine/resolvers/whitespace_resolver.py`
- Test: `tests/test_whitespace_resolver.py`

- [ ] **Step 1: Write the failing test**

`tests/test_whitespace_resolver.py`:
```python
from qa_engine.models import Issue, Member
from qa_engine.resolvers.whitespace_resolver import WhitespaceResolver


def _member(src, tgt, tags=None):
    return Member("1", "g1", src, tgt, {}, tags or {}, "Edited", None, [])


def test_resolves_tag_adjacent_space_as_auto_fix():
    m = _member("⟦1⟧⟦2⟧Perfect Size⟦3⟧", "⟦1⟧ ⟦2⟧ Ιδανικό ⟦3⟧", tags={})
    r = WhitespaceResolver().resolve(Issue("3193", "extra space after tag", "", "g1", "1"), m, None)
    assert r.action == "fix"
    assert r.strategy == "deterministic"
    assert r.needs_approval is False and r.confidence == 1.0
    # new_target is the realigned, detokenized raw inner (no tag-adjacent spaces)
    assert r.new_target == "Ιδανικό"  # tags map empty -> markers dropped in this unit test


def test_no_change_returns_report():
    m = _member("⟦1⟧X⟦2⟧", "⟦1⟧Υ⟦2⟧")
    r = WhitespaceResolver().resolve(Issue("3050", "multiple consecutive whitespaces", "", "g1", "1"), m, None)
    assert r.action == "report"   # nothing to fix (already aligned) -> informational
```

> Note: in `test_resolves_tag_adjacent_space_as_auto_fix` the member's `target_tags` is empty, so `detokenize` drops the `⟦N⟧` markers; the assertion checks the whitespace was removed around them. With a real tag map the markers are restored to tag XML.

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_whitespace_resolver.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `qa_engine/resolvers/whitespace_resolver.py`**

```python
from ..models import Resolution
from ..whitespace import align_whitespace
from ..tags import detokenize
from .base import Resolver


class WhitespaceResolver(Resolver):
    """Deterministic: align the target's tag-boundary/edge whitespace to the
    source. Covers codes 3050, 3071-3076, 3110, 3190-3197. Zero-error by
    construction (only [ \\t] adjacent to tags/edges is changed)."""

    strategy = "deterministic"

    def resolve(self, issue, member, context) -> Resolution:
        new_tok = align_whitespace(member.source_text, member.target_text)
        if new_tok == member.target_text:
            return Resolution(
                action="report", new_target=None, confidence=1.0,
                needs_approval=False, strategy="deterministic",
                rationale="No target whitespace difference vs source for this code.",
            )
        new_inner = detokenize(new_tok, member.target_tags)
        return Resolution(
            action="fix", new_target=new_inner, confidence=1.0,
            needs_approval=False, strategy="deterministic",
            rationale="Aligned target tag-boundary/edge whitespace to the source.",
        )
```

- [ ] **Step 4: Run; verify pass; full suite**

Run: `python -m pytest tests/test_whitespace_resolver.py -v` → PASS (2). Then `python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add qa_engine/resolvers/whitespace_resolver.py tests/test_whitespace_resolver.py
git commit -m "feat: deterministic whitespace resolver (auto-fix, zero AI)"
```

---

### Task 7: AI inconsistency resolver

Wraps the existing case-based inconsistency flow (`build_cases` + `classify_case`) behind the per-code resolver interface. Because inconsistency (3100/3101) is cross-segment, this resolver is a **batch resolver**: the engine calls `resolve_batch(issues, members, ai_client, glossary)` once for all inconsistency issues and gets back per-segment `Resolution`s.

**Files:**
- Create: `qa_engine/resolvers/inconsistency_resolver.py`
- Test: `tests/test_inconsistency_resolver.py`

- [ ] **Step 1: Write the failing test**

`tests/test_inconsistency_resolver.py`:
```python
from pathlib import Path
from qa_engine.parser import parse_issues
from qa_engine.resolvers.inconsistency_resolver import resolve_inconsistencies

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        if "whitespace" in user_content or "typo" in user_content:
            return {"category": "false_positive", "rationale": "ws", "confidence": "high"}
        if "source_inconsistency" in user_content:
            return {"category": "pick_best", "rationale": "std", "confidence": "high",
                    "chosen_variant_key": "Εύκολο στον καθαρισμό"}
        return {"category": "differentiate", "rationale": "colors", "confidence": "high",
                "differentiated": [{"source_key": "Ocean Deep Sand", "new_target": "Άμμος"}]}


def test_resolve_inconsistencies_returns_resolution_per_segment():
    issues, members = parse_issues(FIX.read_bytes())
    by_guid = resolve_inconsistencies(issues, members, _Fake(), glossary={})
    # returns a dict segmentguid -> Resolution for inconsistency-affected segments
    assert isinstance(by_guid, dict)
    # false_positive -> ignore, pick_best/differentiate -> fix
    actions = {r.action for r in by_guid.values()}
    assert actions <= {"fix", "ignore", "report"}
    for r in by_guid.values():
        assert r.strategy == "ai"
        assert 0.0 <= r.confidence <= 1.0
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_inconsistency_resolver.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `qa_engine/resolvers/inconsistency_resolver.py`**

```python
from ..models import Resolution
from ..casebuilder import build_cases
from ..context import build_case_payload
from ..ai import classify_case, build_system_prompt
from ..tags import detokenize

_CONF = {"high": 0.95, "medium": 0.6, "low": 0.3}


def resolve_inconsistencies(issues, members_by_guid, ai_client, glossary):
    """Batch-resolve 3100/3101 inconsistency issues. Returns {segmentguid: Resolution}."""
    members = list(members_by_guid.values())
    cases = build_cases(members)
    if not cases:
        return {}
    gloss_text = "\n".join(f"{k} = {v}" for k, v in (glossary or {}).items())
    system_prompt = build_system_prompt(gloss_text)

    out = {}
    for case in cases:
        payload = build_case_payload(case, members, glossary or {})
        try:
            decision = classify_case(ai_client, payload, system_prompt, model="")
        except Exception as exc:
            for m in case.members:
                out[m.segmentguid] = Resolution(
                    action="report", confidence=0.0, needs_approval=True,
                    strategy="ai", rationale=f"AI error: {exc}")
            continue
        conf = _CONF.get(decision.confidence, 0.3)
        needs = decision.confidence != "high"
        if decision.category == "false_positive":
            for m in case.members:
                out[m.segmentguid] = Resolution(
                    action="ignore", confidence=conf, needs_approval=needs,
                    strategy="ai", rationale=decision.rationale)
        elif decision.category == "pick_best" and decision.chosen_member_id:
            chosen = next((m for m in case.members if m.tu_id == decision.chosen_member_id), None)
            if chosen is None:
                continue
            new_inner = detokenize(chosen.target_text, chosen.target_tags)
            for m in case.members:
                out[m.segmentguid] = Resolution(
                    action="fix", new_target=new_inner, confidence=conf,
                    needs_approval=needs, strategy="ai", rationale=decision.rationale)
        elif decision.category == "differentiate":
            wanted = {d["source_key"]: d["new_target"] for d in decision.differentiated}
            for m in case.members:
                if m.source_text in wanted:
                    from xml.sax.saxutils import escape as _esc
                    try:
                        new_inner = detokenize(_esc(wanted[m.source_text]), m.target_tags)
                    except ValueError:
                        out[m.segmentguid] = Resolution(
                            action="report", confidence=0.0, needs_approval=True,
                            strategy="ai", rationale="AI target dropped a tag marker.")
                        continue
                    out[m.segmentguid] = Resolution(
                        action="fix", new_target=new_inner, confidence=conf,
                        needs_approval=needs, strategy="ai", rationale=decision.rationale)
    return out
```

- [ ] **Step 4: Run; verify pass; full suite**

Run: `python -m pytest tests/test_inconsistency_resolver.py -v` → PASS (1). Then `python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add qa_engine/resolvers/inconsistency_resolver.py tests/test_inconsistency_resolver.py
git commit -m "feat: AI inconsistency resolver (batch, confidence-routed)"
```

---

### Task 8: Engine.analyze → ReviewSession

Orchestrates: parse issues → route each via registry (deterministic per-segment + inconsistency batch) → build `ReviewSession` (auto-applied / pending / report-only).

**Files:**
- Create: `qa_engine/engine.py`
- Test: `tests/test_engine_analyze.py`

- [ ] **Step 1: Write the failing test**

`tests/test_engine_analyze.py`:
```python
from pathlib import Path
from qa_engine.engine import analyze

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        return {"category": "false_positive", "rationale": "ws", "confidence": "high"}


def test_analyze_returns_review_session():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    assert rs.source_lang == "en" and rs.target_lang == "el"
    # every bucket holds ResolvedItem objects with item_id + resolution
    for bucket in (rs.auto_applied, rs.pending, rs.report_only):
        for it in bucket:
            assert it.item_id and it.resolution is not None
    # high-confidence false_positive (needs_approval False) -> auto_applied
    assert all(it.resolution.needs_approval is False for it in rs.auto_applied)
    assert all(it.resolution.needs_approval is True for it in rs.pending)
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_engine_analyze.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `qa_engine/engine.py`**

```python
from .models import ReviewSession, ResolvedItem
from .parser import parse_issues, parse_languages
from .registry import STRATEGY_BY_CODE, register_resolver, get_resolver
from .resolvers.base import normalize_code, ReportOnlyResolver
from .resolvers.whitespace_resolver import WhitespaceResolver
from .resolvers.inconsistency_resolver import resolve_inconsistencies

# Register deterministic resolvers for their codes (one shared instance).
_WS = WhitespaceResolver()
for _code, _strat in STRATEGY_BY_CODE.items():
    if _strat == "deterministic":
        register_resolver(_code, _WS)

_INCONSISTENCY_CODES = {"3100", "3101"}


def analyze(content: bytes, ai_client=None, glossary=None) -> ReviewSession:
    src_lang, tgt_lang = parse_languages(content)
    issues, members = parse_issues(content)

    # Batch AI inconsistency resolution (cross-segment).
    inconsistency_res = {}
    if ai_client is not None and any(normalize_code(i.code) in _INCONSISTENCY_CODES for i in issues):
        inconsistency_res = resolve_inconsistencies(
            [i for i in issues if normalize_code(i.code) in _INCONSISTENCY_CODES],
            members, ai_client, glossary or {})

    auto, pending, report = [], [], []
    for idx, issue in enumerate(issues):
        member = members.get(issue.segmentguid)
        code = normalize_code(issue.code)
        if member is None:
            continue
        if code in _INCONSISTENCY_CODES:
            res = inconsistency_res.get(issue.segmentguid)
            if res is None:
                res = ReportOnlyResolver().resolve(issue, member, None)
        else:
            res = get_resolver(issue).resolve(issue, member, None)

        item = ResolvedItem(
            item_id=f"{issue.segmentguid}:{code}:{idx}",
            segmentguid=issue.segmentguid, tu_id=issue.tu_id,
            code=code, problemname=issue.problemname,
            source_preview=member.source_text,
            current_target_preview=member.target_text,
            proposed_target_preview=res.new_target,
            resolution=res,
        )
        if res.action == "report":
            report.append(item)
        elif res.needs_approval:
            pending.append(item)
        else:
            auto.append(item)

    return ReviewSession(src_lang, tgt_lang, auto, pending, report)
```

- [ ] **Step 4: Run; verify pass; full suite**

Run: `python -m pytest tests/test_engine_analyze.py -v` → PASS (1). Then `python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add qa_engine/engine.py tests/test_engine_analyze.py
git commit -m "feat: engine.analyze routes issues into a ReviewSession"
```

---

### Task 9: Engine.apply → corrected bytes

Applies a set of `ResolvedItem`s (auto-applied + user-approved) to the original mqxliff. Reuses the existing format-preserving, in-memory-validated writer primitives.

**Files:**
- Modify: `qa_engine/apply.py` (add a generic `apply_resolved_items`)
- Modify: `qa_engine/engine.py` (add `apply`)
- Test: `tests/test_engine_apply.py`

- [ ] **Step 1: Write the failing test**

`tests/test_engine_apply.py`:
```python
from pathlib import Path
from lxml import etree
from qa_engine.engine import analyze, apply

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        return {"category": "false_positive", "rationale": "ws", "confidence": "high"}


def test_apply_auto_and_approved_yields_valid_xml():
    content = FIX.read_bytes()
    rs = analyze(content, ai_client=_Fake(), glossary={})
    # approve everything pending as-is
    items = rs.auto_applied + rs.pending
    fixed = apply(content, items)
    etree.fromstring(fixed)                      # valid XML, no exception
    assert isinstance(fixed, bytes)


def test_apply_fix_writes_new_target(tmp_path):
    # craft an item that sets a target
    content = FIX.read_bytes()
    rs = analyze(content, ai_client=_Fake(), glossary={})
    # force one fix item
    from qa_engine.models import Resolution, ResolvedItem
    it = ResolvedItem("g1:x:0", "g1", "1", "3050", "p", "s", "t",
                      "ΝΕΟ", Resolution(action="fix", new_target="ΝΕΟ",
                      confidence=1.0, needs_approval=False, strategy="deterministic"))
    fixed = apply(content, [it]).decode("utf-8-sig")
    import re
    m = re.search(r'segmentguid="g1".*?<target[^>]*>(.*?)</target>', fixed, re.S)
    assert m.group(1) == "ΝΕΟ"
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_engine_apply.py -v`
Expected: FAIL (`apply` not importable from engine).

- [ ] **Step 3: Add `apply_resolved_items` to `qa_engine/apply.py`**

Append (reuses existing `_TU_RE`, `_segguid`, `_set_target`, `_mark_ignored`, `_remove_inconsistency_warnings`):
```python
def apply_resolved_items(content: bytes, items) -> bytes:
    """Apply a list of ResolvedItem to the mqxliff bytes. action == 'fix' sets the
    target inner (and removes that segment's inconsistency warning); action ==
    'ignore' marks the segment's inconsistency warnings ignored; 'report' is skipped."""
    text = content.decode("utf-8-sig")
    by_guid = {}   # segmentguid -> ("settarget", inner) | ("ignore",)
    for it in items:
        act = it.resolution.action
        if act == "fix" and it.resolution.new_target is not None:
            by_guid[it.segmentguid] = ("settarget", it.resolution.new_target)
        elif act == "ignore":
            by_guid.setdefault(it.segmentguid, ("ignore",))

    def edit_block(match):
        block = match.group(0)
        guid = _segguid(block)
        act = by_guid.get(guid)
        if not act:
            return block
        if act[0] == "settarget":
            block = _set_target(block, act[1])
            return _remove_inconsistency_warnings(block)
        if act[0] == "ignore":
            return _mark_ignored(block)
        return block

    new_text = _TU_RE.sub(edit_block, text)
    etree.fromstring(new_text.encode("utf-8"))     # validate before returning
    return new_text.encode("utf-8-sig")
```

- [ ] **Step 4: Add `apply` to `qa_engine/engine.py`**

```python
from .apply import apply_resolved_items


def apply(content: bytes, items) -> bytes:
    """Apply the given ResolvedItems (typically auto_applied + approved pending)
    and return corrected mqxliff bytes."""
    return apply_resolved_items(content, items)
```

- [ ] **Step 5: Run; verify pass; full suite**

Run: `python -m pytest tests/test_engine_apply.py -v` → PASS (2). Then `python -m pytest -q` → all green.

- [ ] **Step 6: Commit**

```bash
git add qa_engine/apply.py qa_engine/engine.py tests/test_engine_apply.py
git commit -m "feat: engine.apply writes auto+approved fixes to corrected bytes"
```

---

### Task 10: CLI over the engine + real-file smoke

Add a thin CLI so the engine is runnable without the web UI: `analyze` prints a JSON ReviewSession + summary; `apply` writes the fixed file from a decisions JSON.

**Files:**
- Create: `qa_engine/engine_cli.py`
- Modify: `qa_engine/__main__.py` (route `qa-analyze` / `qa-apply`)
- Test: `tests/test_engine_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_engine_cli.py`:
```python
import json
from pathlib import Path
from qa_engine.engine_cli import run_qa_analyze

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        return {"category": "false_positive", "rationale": "ws", "confidence": "high"}


def test_qa_analyze_writes_session_json(tmp_path):
    out = tmp_path / "session.json"
    summary = run_qa_analyze(str(FIX), str(out), ai_client=_Fake(), glossary_path=None)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "auto_applied" in data and "pending" in data and "report_only" in data
    assert summary["counts"]["auto_applied"] == len(data["auto_applied"])
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_engine_cli.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `qa_engine/engine_cli.py`**

```python
import json
from dataclasses import asdict
from .engine import analyze, apply
from .glossary import load_glossary


def _session_to_dict(rs):
    def items(bucket):
        return [
            {
                "item_id": it.item_id, "segmentguid": it.segmentguid, "tu_id": it.tu_id,
                "code": it.code, "problemname": it.problemname,
                "source": it.source_preview, "current_target": it.current_target_preview,
                "proposed_target": it.proposed_target_preview,
                **asdict(it.resolution),
            } for it in bucket
        ]
    return {
        "source_lang": rs.source_lang, "target_lang": rs.target_lang,
        "auto_applied": items(rs.auto_applied),
        "pending": items(rs.pending),
        "report_only": items(rs.report_only),
    }


def run_qa_analyze(in_path, out_path, ai_client=None, glossary_path=None):
    content = open(in_path, "rb").read()
    glossary = load_glossary(glossary_path)
    rs = analyze(content, ai_client=ai_client, glossary=glossary)
    data = _session_to_dict(rs)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    counts = {k: len(data[k]) for k in ("auto_applied", "pending", "report_only")}
    print(f"Analyzed: {counts}")
    return {"counts": counts}
```

- [ ] **Step 4: Run; verify pass; full suite**

Run: `python -m pytest tests/test_engine_cli.py -v` → PASS (1). Then `python -m pytest -q` → all green.

- [ ] **Step 5: Real-file smoke (no API — deterministic-only path)**

Run:
```bash
python -c "from qa_engine.engine import analyze; rs=analyze(open('check_gre.mqxliff','rb').read(), ai_client=None, glossary={}); print('auto',len(rs.auto_applied),'pending',len(rs.pending),'report',len(rs.report_only))"
```
Expected: completes without error; `auto` is large (whitespace fixes), `pending`/`report` small. Record the numbers. (No AI → inconsistency issues fall to report.)

- [ ] **Step 6: Commit**

```bash
git add qa_engine/engine_cli.py tests/test_engine_cli.py
git commit -m "feat: engine CLI (qa-analyze) + real-file smoke"
```

---

## Self-Review

**Spec coverage (spec §→task):**
- §2 engine/UI separation, injectable AIClient, bytes I/O, sync → Task 1 (package), Task 4 (AIClient), Task 8/9 (bytes in/out, synchronous). ✓
- §3 Resolver registry & contract (action/new_target/confidence/needs_approval/rationale/strategy) → Task 2 (Resolution), Task 5 (registry + base). ✓
- §4 code→strategy map (deterministic/ai/report_only) → Task 5 `STRATEGY_BY_CODE`. ✓ (Phase 1a wires deterministic + inconsistency; other ai/report codes default to report_only — consistent with phasing §10.)
- §5 routing & confidence (deterministic auto, ai high-conf auto else approval, report→human) → Task 7 (confidence map, needs_approval) + Task 8 (bucket routing). ✓
- §7 apply & memoQ I/O (file; ignore vs fix; validate) → Task 9 (`apply_resolved_items`, in-memory validate, ignore/fix). ✓
- §8 AI provider abstraction → Task 4 (`AIClient` protocol + `ClaudeAIClient`). ✓
- §9 reuse of tested core → Tasks 6/7/9 reuse `whitespace`, `casebuilder`, `ai`, `apply`. ✓
- §6 web UI → **out of scope for this plan (Phase 1b)** — stated in header. The engine exposes `analyze`/`apply` + a JSON session (Task 10) the web UI will consume. ✓ (intentional decomposition, not a gap)

**Placeholder scan:** No TBD/TODO; every code step has complete runnable code. ✓

**Type consistency:** `Resolution`/`ResolvedItem`/`ReviewSession`/`Issue` field names are used identically across Tasks 2/6/7/8/9/10. `AIClient.resolve(system_prompt, user_content, schema)` signature matches its use in Task 4 (`ClaudeAIClient`), Task 7 (`resolve_inconsistencies`), and the test fakes. `classify_case(client, payload, system_prompt, model)` keeps its signature (Task 4) and is called with `model=""` in Task 7. `apply_resolved_items(content, items)` (Task 9) matches `engine.apply` and its test. `normalize_code` is defined once (Task 5 base) and reused in registry + engine. ✓

**Note on `model` param:** Task 4 makes `classify_case`'s `model` argument vestigial (model now lives on the AIClient). Kept in the signature to avoid touching the existing `tests/test_ai.py` call shape; a later cleanup may drop it. Flagged, not a bug.
