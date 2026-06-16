# Phase 1c — Per-Segment AI Resolution (core correction)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Replace the code-routed "deterministic / report-only" model with the user's model: **every flagged segment is handled** — bulk-suitable mechanical codes (whitespace) are auto-fixed in bulk; **every other code is sent to AI per segment**, which either auto-fixes (when safe) or proposes a correction for the user to approve/edit. **No "report-only / left for human review" bucket.**

**Architecture:** Segments are processed in order. For each flagged segment: if all its codes are bulk-suitable → deterministic whitespace fix; otherwise → a single general **AI segment resolver** call that reads the segment's source/target, its memoQ QA code(s) + official description + warning args + neighbor context, and returns a corrected target plus an `auto_apply` judgment. Results bucket into `auto_applied` (deterministic + AI auto) and `pending` (AI suggestions to approve/edit). The grouping-based inconsistency resolver is retired — 3100/3101 go through the general AI resolver using the warning's `localizationargs`.

**Tech Stack:** existing `qa_engine` (parser, tags, whitespace, apply, engine, AIClient), Claude Opus 4.8, pytest. Streamlit UI updated to drop the report-only section.

**Working dir / repo:** `C:\Users\ada\Documents\Claude\Projects\QA resolvers\memoq-qa-resolver` (70 tests pass).

---

### Task 1: QA code descriptions + bulk-suitable set

**Files:**
- Create: `qa_engine/qa_codes.py`
- Test: `tests/test_qa_codes.py`

- [ ] **Step 1: Write the failing test**

`tests/test_qa_codes.py`:
```python
from qa_engine.qa_codes import QA_CODE_DESCRIPTIONS, BULK_SUITABLE_CODES, describe_code


def test_known_descriptions():
    assert "3101" in QA_CODE_DESCRIPTIONS
    assert "translation" in QA_CODE_DESCRIPTIONS["3101"].lower()
    assert "3091" in QA_CODE_DESCRIPTIONS  # terminology


def test_bulk_suitable_is_whitespace_family():
    assert "3050" in BULK_SUITABLE_CODES and "3193" in BULK_SUITABLE_CODES
    assert "3101" not in BULK_SUITABLE_CODES  # judgment -> not bulk


def test_describe_code_falls_back_to_problemname():
    assert describe_code("99999", "some new problem") == "some new problem"
    assert describe_code("3101", "x") == QA_CODE_DESCRIPTIONS["3101"]
```

- [ ] **Step 2: Run; verify failure** — `python -m pytest tests/test_qa_codes.py -v` → FAIL.

- [ ] **Step 3: Implement `qa_engine/qa_codes.py`**

```python
# Official memoQ QA code meanings (from the memoQ docs "QA warnings" page).
# Fed to the AI so it understands each code regardless of UI language.
QA_CODE_DESCRIPTIONS = {
    "1001": "The translation contains extra tags that should be removed.",
    "1002": "Some tags are missing in the translation and must be added.",
    "2004": "Some required tags are missing in the translated text.",
    "2010": "Inline tags in the translation are not well-formed vs the source.",
    "2011": "An inline tag is missing from the translated text.",
    "2015": "There is an extra inline tag in the translation.",
    "2016": "The order of tags in the translation differs from the source.",
    "3020": "Source and translation end with different punctuation marks.",
    "3030": "The first letters of source and translation are capitalized differently.",
    "3040": "The translation is identical to the source.",
    "3061": "A number has a non-standard format for the target language.",
    "3062": "Numbers do not match between source and translation.",
    "3063": "A number from the source is missing in the translation.",
    "3064": "The translation contains an extra number not in the source.",
    "3067": "Strict number formats do not match between source and target.",
    "3068": "A number is formatted differently in source and translation.",
    "3077": "Quotation marks, apostrophes or brackets differ between source and translation.",
    "3078": "A punctuation mark seems incorrect for the target language.",
    "3079": "An incorrect sequence of punctuation marks.",
    "3085": "Repeated (duplicate) words detected in the translation.",
    "3086": "There is an extra quote/bracket punctuation mark.",
    "3087": "A quote/bracket is missing.",
    "3088": "A quote/bracket has no matching pair.",
    "3089": "Source and target quotes/brackets do not match.",
    "3091": "A termbase term is missing from the translation.",
    "3092": "The translation includes an extra term.",
    "3093": "A term is translated with a forbidden translation.",
    "3094": "A non-translatable element is missing from the translation.",
    "3095": "An extra non-translatable element is in the translation.",
    "3096": "The count of a non-translatable element differs from the source.",
    "3097": "A forbidden term was used; a different term should be used.",
    "3100": "Same source segment translated in two different ways (inconsistent).",
    "3101": "Two different source segments have the same translation (inconsistent).",
    "3120": "The translation contains a forbidden character.",
    "3131": "Bold/italic/underline formatting is missing in the translation.",
    "3132": "Extra bold/italic/underline formatting in the translation.",
    "3133": "Bold/italic/underline formatting differs from the source.",
}

# Codes safe to fix mechanically in bulk (no AI judgment needed): whitespace family.
BULK_SUITABLE_CODES = {
    "3050", "3071", "3072", "3073", "3074", "3075", "3076",
    "3110", "3190", "3191", "3192", "3193", "3194", "3195", "3196", "3197",
}


def describe_code(code: str, problemname: str = "") -> str:
    """Official description for a code; fall back to the warning's problemname."""
    return QA_CODE_DESCRIPTIONS.get(code, problemname or f"QA code {code}")
```

- [ ] **Step 4: Run; pass; full suite green.**
- [ ] **Step 5: Commit** — `feat: QA code descriptions + bulk-suitable set`

---

### Task 2: General per-segment AI resolver

**Files:**
- Create: `qa_engine/resolvers/ai_segment_resolver.py`
- Test: `tests/test_ai_segment_resolver.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ai_segment_resolver.py`:
```python
from qa_engine.models import Issue, Member
from qa_engine.resolvers.ai_segment_resolver import resolve_segment, SEGMENT_SCHEMA


class _Fake:
    def __init__(self, payload):
        self.payload = payload
        self.last = None
    def resolve(self, system_prompt, user_content, schema):
        self.last = (system_prompt, user_content, schema)
        return self.payload


def _member(src, tgt, tags=None):
    return Member("5", "g5", src, tgt, {}, tags or {}, "Edited", None, [])


def test_auto_apply_fix():
    fake = _Fake({"fixed_target": "Άμμος", "auto_apply": True, "confidence": "high",
                  "rationale": "distinct color"})
    issues = [Issue("3101", "inconsistent translation", "Sand\tΆμμος", "g5", "5")]
    res = resolve_segment(_member("Sand", "Σοφιστικέ"), issues, context=None, ai_client=fake)
    assert res.action == "fix" and res.new_target == "Άμμος"
    assert res.needs_approval is False and res.strategy == "ai"
    # the schema was passed, and the code description reached the prompt
    assert fake.last[2] == SEGMENT_SCHEMA
    assert "inconsistent" in fake.last[1].lower()


def test_needs_approval_when_not_auto():
    fake = _Fake({"fixed_target": "Νέο", "auto_apply": False, "confidence": "medium",
                  "rationale": "uncertain"})
    issues = [Issue("3091", "missing term", "x", "g5", "5")]
    res = resolve_segment(_member("X", "Y"), issues, context=None, ai_client=fake)
    assert res.action == "fix" and res.needs_approval is True


def test_marker_mismatch_falls_back_to_needs_approval_report():
    # AI returned a target with a bogus marker not in the segment's tags
    fake = _Fake({"fixed_target": "Νέο ⟦9⟧", "auto_apply": True, "confidence": "high",
                  "rationale": "x"})
    issues = [Issue("3101", "inconsistent translation", "x", "g5", "5")]
    res = resolve_segment(_member("X", "Y", tags={}), issues, context=None, ai_client=fake)
    # cannot safely detokenize -> keep as a suggestion needing human approval, never auto
    assert res.needs_approval is True
```

- [ ] **Step 2: Run; verify failure.**

- [ ] **Step 3: Implement `qa_engine/resolvers/ai_segment_resolver.py`**

```python
import json
from xml.sax.saxutils import escape as _xml_escape
from ..models import Resolution
from ..tags import detokenize, markers_in
from ..qa_codes import describe_code

SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "fixed_target": {"type": "string"},
        "auto_apply": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string"},
    },
    "required": ["fixed_target", "auto_apply", "confidence", "rationale"],
    "additionalProperties": False,
}

_SYSTEM = """You fix one translation segment that memoQ's QA flagged (any language pair).
Inline tags are shown as markers like ⟦1⟧ — keep every marker exactly, never add or drop one.
You are given the QA issue(s) with their official meaning, the source, the current target, and
the localization args memoQ provided. Return the corrected target. Set auto_apply=true ONLY when
the fix is unambiguous and safe (e.g. a clear mechanical or factual correction); set auto_apply=false
when a human should confirm (anything requiring stylistic/semantic judgment, terminology choices,
restructuring, or where you are not fully certain). If the current target is already correct for the
flagged issue, return it unchanged with auto_apply=true and say so in the rationale."""


def _build_user(member, issues):
    lines = ["ISSUES on this segment:"]
    for i in issues:
        lines.append(f"- code {i.code}: {describe_code(i.code, i.problemname)}"
                     + (f"  [details: {i.args}]" if i.args else ""))
    lines.append(f"\nSOURCE: {member.source_text}")
    lines.append(f"CURRENT TARGET: {member.target_text}")
    lines.append("\nReturn the corrected target (keep all ⟦N⟧ markers).")
    return "\n".join(lines)


def resolve_segment(member, issues, context, ai_client) -> Resolution:
    user = _build_user(member, issues)
    try:
        data = ai_client.resolve(_SYSTEM, user, SEGMENT_SCHEMA)
    except Exception as exc:
        return Resolution(action="report", confidence=0.0, needs_approval=True,
                          strategy="ai", rationale=f"AI error: {exc}")
    fixed_tok = data["fixed_target"]
    conf = {"high": 0.95, "medium": 0.6, "low": 0.3}.get(data.get("confidence"), 0.3)
    # detokenize defensively: markers must match the segment's tag map
    try:
        new_inner = detokenize(_xml_escape(fixed_tok), member.target_tags) \
            if member.target_tags else detokenize(fixed_tok, member.target_tags)
        bad_markers = False
    except ValueError:
        bad_markers = True
    if bad_markers:
        return Resolution(action="fix", new_target=None, confidence=conf,
                          needs_approval=True, strategy="ai",
                          rationale="AI changed the tag markers; please review/fix manually. "
                                    + data.get("rationale", ""))
    needs = (not data.get("auto_apply", False))
    return Resolution(action="fix", new_target=new_inner, confidence=conf,
                      needs_approval=needs, strategy="ai", rationale=data.get("rationale", ""))
```

> Note on escaping: when `target_tags` is non-empty the markers map to tag XML and the surrounding text must be XML-escaped; when empty, `detokenize` just validates there are no stray markers and returns the text. The test `test_marker_mismatch...` uses empty tags + a bogus `⟦9⟧` so `detokenize` raises → `needs_approval=True`.

- [ ] **Step 4: Run; pass; full suite green.**
- [ ] **Step 5: Commit** — `feat: general per-segment AI resolver (handles any QA code)`

---

### Task 3: Rewrite engine.analyze — per-segment routing, no report-only dump

**Files:**
- Modify: `qa_engine/engine.py`
- Test: `tests/test_engine_per_segment.py`

- [ ] **Step 1: Write the failing test**

`tests/test_engine_per_segment.py`:
```python
from pathlib import Path
from qa_engine.engine import analyze

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        return {"fixed_target": "ΔΙΟΡΘΩΜΕΝΟ", "auto_apply": False,
                "confidence": "high", "rationale": "fix"}


def test_no_report_only_bucket_when_ai_present():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    # every inconsistency (3101) segment got an AI suggestion -> pending, not report
    assert len(rs.report_only) == 0
    assert all(it.resolution.strategy in ("deterministic", "ai") for it in rs.pending)
    # pending items carry a concrete proposed target
    assert all(it.proposed_target_preview for it in rs.pending)


def test_segments_processed_in_order():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    ids = [int(it.tu_id) for it in (rs.auto_applied + rs.pending)]
    assert ids == sorted(ids)


def test_without_ai_judgment_codes_still_listed_not_silently_dropped():
    # no ai_client -> judgment codes can't be AI-resolved; they must surface as
    # pending "needs manual" (NOT silently dropped, NOT auto-applied)
    rs = analyze(FIX.read_bytes(), ai_client=None, glossary={})
    assert len(rs.pending) >= 1
```

- [ ] **Step 2: Run; verify failure** (current engine still has report_only/grouping behavior).

- [ ] **Step 3: Rewrite the routing in `qa_engine/engine.py`**

Replace the body of `analyze` (keep the import-time `WhitespaceResolver` registration and `session_to_view`/`items_for_apply`/`apply`). New `analyze`:
```python
from .qa_codes import BULK_SUITABLE_CODES, describe_code
from .resolvers.ai_segment_resolver import resolve_segment
from .resolvers.whitespace_resolver import WhitespaceResolver
from .resolvers.base import normalize_code
from .models import ReviewSession, ResolvedItem, Resolution

_WS = WhitespaceResolver()


def analyze(content: bytes, ai_client=None, glossary=None) -> ReviewSession:
    src_lang, tgt_lang = parse_languages(content)
    issues, members = parse_issues(content)

    # group issues by segment, preserve segment order (by numeric tu_id)
    by_seg = {}
    for it in issues:
        by_seg.setdefault(it.segmentguid, []).append(it)
    ordered_guids = sorted(by_seg, key=lambda g: int(by_seg[g][0].tu_id)
                           if by_seg[g][0].tu_id.isdigit() else 0)

    auto, pending = [], []
    for guid in ordered_guids:
        seg_issues = by_seg[guid]
        member = members.get(guid)
        if member is None:
            continue
        codes = [normalize_code(i.code) for i in seg_issues]
        all_bulk = all(c in BULK_SUITABLE_CODES for c in codes)

        if all_bulk:
            res = _WS.resolve(seg_issues[0], member, None)
        elif ai_client is not None:
            res = resolve_segment(member, seg_issues, None, ai_client)
        else:
            # no AI available -> surface as a suggestion needing manual handling,
            # never silently dropped, never auto-applied
            res = Resolution(action="fix", new_target=None, confidence=0.0,
                             needs_approval=True, strategy="ai",
                             rationale="AI is required to resolve "
                                       + ", ".join(sorted(set(codes)))
                                       + "; enable AI or fix manually.")

        primary = seg_issues[0]
        item = ResolvedItem(
            item_id=f"{guid}:{primary.code}",
            segmentguid=guid, tu_id=primary.tu_id,
            code=primary.code, problemname=primary.problemname,
            source_preview=member.source_text,
            current_target_preview=member.target_text,
            proposed_target_preview=res.new_target if res.new_target is not None
                                     else member.target_text,
            resolution=res,
        )
        # deterministic no-op (whitespace already aligned) -> nothing to do; skip it
        if res.action == "fix" and res.new_target is None and res.strategy == "deterministic":
            continue
        if res.action == "report" and res.new_target is None and res.strategy == "deterministic":
            continue
        if res.needs_approval:
            pending.append(item)
        else:
            auto.append(item)

    return ReviewSession(src_lang, tgt_lang, auto, pending, report_only=[])
```

> The `report_only` field stays on `ReviewSession` (for back-compat with `session_to_view`) but is always empty now — the model no longer dumps anything there. The whitespace resolver returning `action="report"` for a true no-op (already-aligned) means "nothing to fix" and is correctly skipped, not surfaced.

- [ ] **Step 4: Run; pass; full suite.** Some old tests (`test_engine_analyze.py`, `test_inconsistency_resolver.py`) assert the OLD report_only/grouping behavior and will now fail — update or remove them: delete `tests/test_inconsistency_resolver.py` (the grouping resolver is retired) and update `tests/test_engine_analyze.py` to the new buckets (no report_only). Keep `test_engine_apply.py`, `test_engine_glue.py`, `test_engine_cli.py` working (adjust any report_only assumptions).

- [ ] **Step 5: Commit** — `feat: per-segment AI routing; retire report-only dump and grouping resolver`

---

### Task 4: Update Streamlit UI — drop report-only, frame as AI review

**Files:**
- Modify: `streamlit_app.py`
- Test: `tests/test_streamlit_app.py` (smoke still passes)

- [ ] **Step 1:** Update `streamlit_app.py`: remove the "Report-only — manual review" expander block entirely. Change the metrics to two columns: "Auto-fixed" (len auto_applied) and "Needs your approval" (len pending). Keep the auto-applied expander and the per-pending approve/edit cards and the Apply/download button. Update the intro caption to: "The AI checks each flagged segment and either fixes it automatically or proposes a fix for you to approve or edit."

- [ ] **Step 2:** Run `python -m pytest tests/test_streamlit_app.py -v` → 2 pass (the smoke test only checks load + title, still valid). Then `python -m pytest -q` → all green.

- [ ] **Step 3:** `python -c "import streamlit_app"` → no exception.

- [ ] **Step 4: Commit** — `feat: Streamlit UI reflects per-segment AI model (no report-only)`

---

### Task 5: Real-file smoke + verify

- [ ] **Step 1 (no API):** `python -c "from qa_engine.engine import analyze; rs=analyze(open(r'../Inconsistency/check_gre.mqxliff','rb').read(), ai_client=None, glossary={}); print('auto',len(rs.auto_applied),'pending',len(rs.pending),'report',len(rs.report_only))"` — expect: auto large (whitespace bulk), pending = the judgment segments (3101/3085) surfaced for manual/AI (NOT dumped to report), report 0. Record numbers.
- [ ] **Step 2:** Confirm `grep -rn "import streamlit\|import fastapi" qa_engine` is empty.
- [ ] **Step 3:** Full suite green. No commit needed beyond Tasks 1-4.

---

## Self-Review

- **User model (every flagged segment → auto-fix or AI suggestion; no report dump):** Task 3 routes each segment; bulk→deterministic auto, else→AI (`resolve_segment`) producing a concrete suggestion; `report_only` always empty. Without AI, judgment segments surface as pending-needs-manual, never silently dropped. ✓
- **Sequential by segment number:** Task 3 sorts guids by numeric tu_id. ✓
- **Bulk only for suitable codes:** `BULK_SUITABLE_CODES` (whitespace family) in Task 1; everything else → AI. ✓
- **AI reads code + meaning + segment:** Task 2 prompt includes `describe_code` + source/target/args. ✓
- **Retire grouping inconsistency resolver:** Task 3 Step 4 deletes its test; 3100/3101 now flow through `resolve_segment`. ✓
- **UI:** Task 4 drops report-only. ✓
- **Type consistency:** `resolve_segment(member, issues, context, ai_client)`, `ResolvedItem`/`Resolution` reused; `ReviewSession.report_only` kept (empty) so `session_to_view`/`items_for_apply` unchanged. ✓
- **Input modes:** Mode B (embedded codes) implemented. Mode A (HTML report) deferred — the embedded codes carry identical data reliably; a pluggable report parser can feed the same `issues` list later.
