# Phase 1f — False-positive "ignore" verdict + risky-code gating

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Let the per-segment AI decide a flag is a **false positive** (translation already correct — e.g. `&quot;` entity in a URL, a brand name/date correctly kept identical) and **mark it `ignored`** (memoQ ignore flag) instead of changing the correct translation. High-confidence false positives auto-ignore; low-confidence go to approval. Risky tag-structure codes (2010/2011/2015/2016) always go to approval, never auto.

**Architecture:** `resolve_segment` returns a `verdict` of `fix` or `false_positive`. `false_positive` → `Resolution(action="ignore")`. `apply` marks the segment's QA warnings `ignored` for `action="ignore"` (generalized from inconsistency-only to any code). The engine forces `needs_approval=True` for risky codes.

**Tech Stack:** existing `qa_engine`, Claude, pytest. **Repo:** `C:\Users\ada\Documents\Claude\Projects\QA resolvers\memoq-qa-resolver` (84 tests pass).

**Caveat to verify in memoQ:** whether the `mq:errorwarning-ignored` flag survives a fresh QA re-run after import — if not, true false positives stay in the report (the translation remains correct either way).

---

### Task 1: RISKY_CODES + false-positive verdict in the AI resolver

**Files:**
- Modify: `qa_engine/qa_codes.py` (add `RISKY_CODES`)
- Modify: `qa_engine/resolvers/ai_segment_resolver.py`
- Test: `tests/test_ai_segment_resolver.py` (extend)

- [ ] **Step 1: Write failing tests** — append to `tests/test_ai_segment_resolver.py`:
```python
def test_false_positive_high_conf_auto_ignores():
    fake = _Fake({"verdict": "false_positive", "fixed_target": "",
                  "auto_apply": True, "confidence": "high",
                  "rationale": "';' is part of the &quot; entity; source==target; not a real error"})
    issues = [Issue("3073", "space missing after sign", ";", "g5", "5")]
    res = resolve_segment(_member("&quot;https://x", "&quot;https://x"), issues, None, fake)
    assert res.action == "ignore" and res.needs_approval is False and res.strategy == "ai"


def test_false_positive_low_conf_needs_approval():
    fake = _Fake({"verdict": "false_positive", "fixed_target": "",
                  "auto_apply": False, "confidence": "low", "rationale": "maybe"})
    res = resolve_segment(_member("X", "X"), [Issue("3100", "inconsistent", "", "g5", "5")], None, fake)
    assert res.action == "ignore" and res.needs_approval is True


def test_fix_verdict_still_fixes():
    fake = _Fake({"verdict": "fix", "fixed_target": "Άμμος", "auto_apply": True,
                  "confidence": "high", "rationale": "distinct color"})
    res = resolve_segment(_member("Sand", "Σοφιστικέ"), [Issue("3101","inc","","g5","5")], None, fake)
    assert res.action == "fix" and res.new_target == "Άμμος" and res.needs_approval is False
```
(The existing tests used a payload without `verdict`; update the existing `_Fake` payloads in this file to include `"verdict": "fix"` so they still represent a fix. Where an existing test omits `verdict`, the resolver must default a missing `verdict` to `"fix"` for backward-safety.)

- [ ] **Step 2: Run; verify failure.**

- [ ] **Step 3: Add `RISKY_CODES` to `qa_engine/qa_codes.py`:**
```python
# Tag-structure codes where an automatic fix can corrupt the file; never auto-apply.
RISKY_CODES = {"1001", "1002", "2004", "2010", "2011", "2015", "2016"}
```

- [ ] **Step 4: Update `qa_engine/resolvers/ai_segment_resolver.py`:**
  - Add `"verdict"` to `SEGMENT_SCHEMA` properties: `"verdict": {"type": "string", "enum": ["fix", "false_positive"]}` and add it to `required`. Keep `fixed_target` required (may be `""` for false_positive).
  - Extend `_SYSTEM` with a false-positive paragraph:
    ```
    Decide a verdict. Use "false_positive" when the current target is already correct and the
    QA flag is a mechanical artifact — e.g. the flagged sign is part of an HTML entity like
    &quot; or &amp;, the segment is a brand name / code / date correctly kept identical to the
    source, or the source has the very same pattern. For a false_positive, DO NOT change the
    translation; it will be marked "ignored" in memoQ. Use "fix" only for a genuine error, and
    then return the corrected target. Set auto_apply=true only when you are confident.
    ```
  - In `resolve_segment`, read `verdict = data.get("verdict", "fix")`. If `verdict == "false_positive"`:
    ```python
        conf = {"high": 0.95, "medium": 0.6, "low": 0.3}.get(data.get("confidence"), 0.3)
        needs = not (data.get("auto_apply", False) and data.get("confidence") == "high")
        return Resolution(action="ignore", new_target=None, confidence=conf,
                          needs_approval=needs, strategy="ai",
                          rationale=data.get("rationale", ""))
    ```
    Otherwise keep the existing fix path (detokenize, marker guard, auto/approve).

- [ ] **Step 5: Run task tests + full suite → green.**
- [ ] **Step 6: Commit** — `feat: AI false-positive verdict (action=ignore) + RISKY_CODES`

---

### Task 2: Engine — risky-code gating + ignore routing

**Files:**
- Modify: `qa_engine/engine.py`
- Test: `tests/test_engine_ignore.py`

- [ ] **Step 1: Write failing test** `tests/test_engine_ignore.py`:
```python
from qa_engine.engine import analyze

def _doc(code, problemname, src, tgt):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
        f'<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
        f'<source xml:space="preserve">{src}</source>\n'
        f'<target xml:space="preserve">{tgt}</target>\n'
        f'<mq:warnings40><mq:errorwarning mq:errorwarning-code="{code}" mq:errorwarning-problemname="{problemname}" mq:errorwarning-localizationargs="x" /></mq:warnings40>\n'
        '</trans-unit></body></file></xliff>\n'
    ).encode("utf-8")


class _FP:
    def resolve(self, s, u, sch):
        return {"verdict": "false_positive", "fixed_target": "", "auto_apply": True,
                "confidence": "high", "rationale": "entity, not a real error"}


class _Fix:
    def resolve(self, s, u, sch):
        return {"verdict": "fix", "fixed_target": "X", "auto_apply": True,
                "confidence": "high", "rationale": "fix"}


def test_high_conf_false_positive_goes_to_auto_ignore():
    rs = analyze(_doc("03073", "space missing after sign", "A;B", "A;B"), ai_client=_FP(), glossary={})
    assert len(rs.auto_applied) == 1
    assert rs.auto_applied[0].resolution.action == "ignore"


def test_risky_code_never_auto_even_if_ai_says_so():
    # 2016 is risky -> forced to pending regardless of auto_apply=True
    rs = analyze(_doc("02016", "changed tag order", "A", "B"), ai_client=_Fix(), glossary={})
    assert len(rs.auto_applied) == 0 and len(rs.pending) == 1
```

- [ ] **Step 2: Run; verify failure.**

- [ ] **Step 3: Update `qa_engine/engine.py`** — import `RISKY_CODES` from `.qa_codes`; after computing `res` for a segment (both AI and no-AI branches), force approval for risky codes:
```python
        if any(c in RISKY_CODES for c in codes):
            from dataclasses import replace
            res = replace(res, needs_approval=True)
```
Place this right before building the `ResolvedItem`. The existing bucketing (`action=="report"`→report skip; `needs_approval`→pending; else→auto) then handles `action=="ignore"` correctly (auto-ignore vs pending-ignore). Ensure an `action=="ignore"` item is NOT caught by the deterministic no-op skip (it won't be — that skip checks `strategy=="deterministic"`).

- [ ] **Step 4: Run task tests + full suite → green.**
- [ ] **Step 5: Commit** — `feat: engine gates risky codes to approval; routes ignore verdicts`

---

### Task 3: Apply — generalize ignore to any code

**Files:**
- Modify: `qa_engine/apply.py`
- Test: `tests/test_apply_ignore.py`

- [ ] **Step 1: Write failing test** `tests/test_apply_ignore.py`:
```python
from qa_engine.models import Resolution, ResolvedItem
from qa_engine.apply import apply_resolved_items

DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
    '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
    '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
    '<source xml:space="preserve">A;B</source>\n'
    '<target xml:space="preserve">A;B</target>\n'
    '<mq:warnings40><mq:errorwarning mq:errorwarning-code="03073" mq:errorwarning-problemname="space missing after sign" mq:errorwarning-localizationargs="x" /></mq:warnings40>\n'
    '</trans-unit></body></file></xliff>\n'
).encode("utf-8")


def test_ignore_marks_any_code_warning_ignored():
    it = ResolvedItem("g1:3073", "g1", "1", "3073", "p", "A;B", "A;B", "A;B",
                      Resolution(action="ignore", needs_approval=False, strategy="ai"))
    out = apply_resolved_items(DOC, [it]).decode("utf-8-sig")
    assert 'mq:errorwarning-ignored="errorwarning-ignored"' in out  # 3073 warning marked ignored
    assert "A;B" in out                                              # translation untouched
```

- [ ] **Step 2: Run; verify failure** (current `_mark_ignored` only marks `inconsistent translation`).

- [ ] **Step 3: Generalize `_mark_ignored` in `qa_engine/apply.py`** — remove the `inconsistent translation` filter so it marks every `<mq:errorwarning>` on the segment that lacks the ignored attribute:
```python
def _mark_ignored(block: str) -> str:
    def repl(m):
        ew = m.group(0)
        if "errorwarning-ignored=" in ew:
            return ew
        return ew[:-2].rstrip() + ' mq:errorwarning-ignored="errorwarning-ignored" />'
    return re.sub(r"<mq:errorwarning\b[^>]*/>", repl, block)
```
(No change to the `edit_block` routing — `action=="ignore"` already calls `_mark_ignored`.)

- [ ] **Step 4: Run task tests + full suite → green** (check no existing apply test relied on `_mark_ignored` skipping non-inconsistency warnings; update if needed).
- [ ] **Step 5: Commit** — `feat: apply marks any QA code ignored for false-positive verdicts`

---

### Task 4: Streamlit UI — split auto into Fixed vs Ignored

**Files:**
- Modify: `streamlit_app.py`
- Test: `tests/test_streamlit_app.py` (smoke still passes)

- [ ] **Step 1:** In `streamlit_app.py`, split `auto_applied` for display by `action`: items with `action == "ignore"` → a "False-positive (ignored)" expander; `action == "fix"` → "Auto-fixed". Change the metrics to three: "Auto-fixed" (auto fix count), "Marked false-positive" (auto ignore count), "Needs your approval" (pending count). The pending cards already show approve/edit (an ignore-verdict pending item shows its rationale; approving it applies the ignore — keep the same approve flow; the edit box for an ignore item can stay but is irrelevant, that's fine). Keep Apply & download.

Concretely compute:
```python
auto_fixes = [r for r in view["auto_applied"] if r["action"] != "ignore"]
auto_ignores = [r for r in view["auto_applied"] if r["action"] == "ignore"]
```
Render `auto_fixes` in the existing "Auto-fixed" expander; add an "False-positive (ignored)" expander listing `auto_ignores` (code, segment, rationale).

- [ ] **Step 2:** `python -m pytest tests/test_streamlit_app.py -v` → 2 pass; `python -m pytest -q` → all green; `python -c "import streamlit_app"` → no exception.
- [ ] **Step 3: Commit** — `feat: UI shows fixed vs false-positive (ignored) vs needs-approval`

---

### Task 5: Verify

- [ ] **Step 1:** `python -m pytest -q` → all green. Record count.
- [ ] **Step 2:** `grep -rn "import streamlit\|import fastapi" qa_engine` → empty.
- [ ] **Step 3:** No-API real-file smoke on `../Inconsistency/check_gre.mqxliff`: `analyze(..., ai_client=None)` still runs; confirm no crash, no markers in `apply(auto_applied)` output. (Without AI, no false_positive verdicts are produced — that path needs the AI; this just confirms no regression.)
- [ ] **Step 4:** No commit needed beyond Tasks 1-4.

---

## Self-Review
- **False-positive → ignore (user decision 1):** Task 1 verdict + Task 3 apply mark-ignored. ✓
- **High-conf auto-ignore, low → approval (decision 2):** Task 1 `needs = not (auto_apply and confidence=="high")`. ✓
- **Risky tag codes always approval (decision 3):** Task 2 `RISKY_CODES` force `needs_approval=True`. ✓
- **Translation untouched on ignore:** `action=="ignore"` never sets a target; Task 3 test asserts the target is unchanged. ✓
- **No marker/corruption regression:** apply's existing marker guard + XML validation untouched. ✓
- **Type consistency:** `Resolution(action="ignore", ...)`, `resolve_segment` verdict default `"fix"`, `RISKY_CODES` imported in engine. ✓
