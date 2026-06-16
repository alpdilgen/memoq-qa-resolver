# Phase 1b — Streamlit App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** A standalone Streamlit web app over `qa_engine` so users can upload a memoQ `.mqxliff`, see auto-applied fixes, approve/edit/reject the items that need human judgment, and download the corrected file — pushable to GitHub and runnable on Streamlit.

**Architecture:** All selection/edit logic lives in the UI-agnostic engine (`engine.items_for_apply`, `engine.session_to_view`) so it is unit-tested and reusable by the later AnovaAITool integration. `streamlit_app.py` is a thin front-end that only calls `analyze` / `session_to_view` / `items_for_apply` / `apply`.

**Tech Stack:** Streamlit, `qa_engine`, `anthropic` (Claude, optional), pytest + `streamlit.testing.v1.AppTest`.

**Working dir / repo:** `C:\Users\ada\Documents\Claude\Projects\QA resolvers\memoq-qa-resolver` (fresh git repo; 65 tests pass).

---

### Task 1: Engine glue — `session_to_view` + `items_for_apply`

**Files:**
- Modify: `qa_engine/engine.py`
- Modify: `qa_engine/engine_cli.py` (reuse `session_to_view`)
- Test: `tests/test_engine_glue.py`

- [ ] **Step 1: Write the failing test**

`tests/test_engine_glue.py`:
```python
from pathlib import Path
from qa_engine.engine import analyze, session_to_view, items_for_apply

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        return {"category": "false_positive", "rationale": "ws", "confidence": "high"}


def test_session_to_view_shape():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    v = session_to_view(rs)
    assert set(v) == {"source_lang", "target_lang", "auto_applied", "pending", "report_only"}
    for bucket in ("auto_applied", "pending", "report_only"):
        for row in v[bucket]:
            assert {"item_id", "code", "tu_id", "source", "current_target",
                    "proposed_target", "action", "confidence", "rationale"} <= set(row)


def test_items_for_apply_includes_auto_and_only_approved_pending():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    # approve none -> only auto_applied
    items = items_for_apply(rs, approved_ids=set(), edits={})
    assert len(items) == len(rs.auto_applied)
    # approve one pending (if any) -> included
    if rs.pending:
        pid = rs.pending[0].item_id
        items2 = items_for_apply(rs, approved_ids={pid}, edits={})
        assert any(it.item_id == pid for it in items2)


def test_items_for_apply_applies_edit():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    if not rs.pending:
        return
    pid = rs.pending[0].item_id
    items = items_for_apply(rs, approved_ids={pid}, edits={pid: "ΧΕΙΡΟΚΙΝΗΤΟ"})
    edited = next(it for it in items if it.item_id == pid)
    assert edited.resolution.action == "fix"
    assert edited.resolution.new_target == "ΧΕΙΡΟΚΙΝΗΤΟ"
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_engine_glue.py -v`
Expected: FAIL (`ImportError: cannot import name 'session_to_view'`).

- [ ] **Step 3: Implement in `qa_engine/engine.py`** (append; add `from dataclasses import replace` and `from xml.sax.saxutils import escape as _xml_escape` to imports)

```python
def session_to_view(session) -> dict:
    """Serializable view-model of a ReviewSession for any front-end."""
    def rows(bucket):
        out = []
        for it in bucket:
            r = it.resolution
            out.append({
                "item_id": it.item_id, "code": it.code, "tu_id": it.tu_id,
                "problemname": it.problemname, "source": it.source_preview,
                "current_target": it.current_target_preview,
                "proposed_target": it.proposed_target_preview,
                "action": r.action, "confidence": r.confidence,
                "needs_approval": r.needs_approval, "strategy": r.strategy,
                "rationale": r.rationale,
            })
        return out
    return {
        "source_lang": session.source_lang, "target_lang": session.target_lang,
        "auto_applied": rows(session.auto_applied),
        "pending": rows(session.pending),
        "report_only": rows(session.report_only),
    }


def items_for_apply(session, approved_ids, edits=None):
    """Return the ResolvedItems to apply: all auto_applied + approved pending.
    For an approved pending item with an edit, force action='fix' with the
    edited target text (written verbatim; engine.apply validates the XML)."""
    edits = edits or {}
    out = list(session.auto_applied)
    approved_ids = set(approved_ids or ())
    for it in session.pending:
        if it.item_id not in approved_ids:
            continue
        edited = edits.get(it.item_id)
        if edited is not None and edited != (it.resolution.new_target or ""):
            new_res = replace(it.resolution, action="fix", new_target=edited)
            out.append(replace(it, resolution=new_res))
        else:
            out.append(it)
    return out
```

- [ ] **Step 4: Refactor `engine_cli._session_to_dict` to delegate** — replace its body with `from .engine import session_to_view` and `return session_to_view(rs)`. (Keep `run_qa_analyze` working; its test still passes because the dict shape is a superset of what it asserted.)

Concretely, in `qa_engine/engine_cli.py` change `_session_to_dict(rs)` to:
```python
def _session_to_dict(rs):
    from .engine import session_to_view
    return session_to_view(rs)
```

- [ ] **Step 5: Run; verify pass; full suite**

Run: `python -m pytest tests/test_engine_glue.py tests/test_engine_cli.py -v` → pass; then `python -m pytest -q` → all green.

- [ ] **Step 6: Commit**

```bash
git add qa_engine/engine.py qa_engine/engine_cli.py tests/test_engine_glue.py
git commit -m "feat: engine glue (session_to_view, items_for_apply) for front-ends"
```
End with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 2: Streamlit app + smoke test

**Files:**
- Create: `streamlit_app.py`
- Test: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write the failing smoke test** (uses Streamlit's official AppTest harness)

`tests/test_streamlit_app.py`:
```python
from streamlit.testing.v1 import AppTest


def test_app_loads_and_shows_title():
    at = AppTest.from_file("streamlit_app.py").run(timeout=10)
    assert not at.exception
    assert any("memoQ QA Resolver" in t.value for t in at.title)


def test_app_shows_uploader_before_analysis():
    at = AppTest.from_file("streamlit_app.py").run(timeout=10)
    # no ReviewSession yet -> an info/uploader prompt is present, no crash
    assert not at.exception
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_streamlit_app.py -v`
Expected: FAIL (`streamlit_app.py` does not exist).

- [ ] **Step 3: Implement `streamlit_app.py`**

```python
import streamlit as st

from qa_engine.engine import analyze, apply, session_to_view, items_for_apply
from qa_engine.aiclient import ClaudeAIClient

st.set_page_config(page_title="memoQ QA Resolver", layout="wide")
st.title("memoQ QA Resolver")
st.caption("Upload a memoQ .mqxliff (with QA already run). The engine auto-fixes "
           "what it can prove correct and asks you to approve the rest.")

# --- Sidebar: AI settings ---
st.sidebar.header("Settings")
use_ai = st.sidebar.checkbox("Use AI resolvers (Claude)", value=True)
default_key = ""
try:
    default_key = st.secrets.get("anthropic_api_key", "")
except Exception:
    default_key = ""
api_key = st.sidebar.text_input("Anthropic API key", value=default_key, type="password")
st.sidebar.caption("Without a key, only deterministic fixes run; AI-judgment issues "
                   "are reported for manual handling.")

uploaded = st.file_uploader("memoQ .mqxliff", type=["mqxliff"])

if uploaded is not None and st.button("Analyze QA issues", type="primary"):
    content = uploaded.read()
    ai_client = None
    if use_ai and api_key:
        import anthropic
        ai_client = ClaudeAIClient(anthropic.Anthropic(api_key=api_key))
    with st.spinner("Resolving QA issues..."):
        rs = analyze(content, ai_client=ai_client, glossary={})
    st.session_state["rs"] = rs
    st.session_state["content"] = content

rs = st.session_state.get("rs")
if rs is None:
    st.info("Upload a file and click **Analyze QA issues** to begin.")
    st.stop()

view = session_to_view(rs)
c1, c2, c3 = st.columns(3)
c1.metric("Auto-applied", len(view["auto_applied"]))
c2.metric("Needs approval", len(view["pending"]))
c3.metric("Report-only", len(view["report_only"]))

with st.expander(f"Auto-applied fixes ({len(view['auto_applied'])})"):
    st.dataframe([{"code": r["code"], "segment": r["tu_id"],
                   "before": r["current_target"], "after": r["proposed_target"]}
                  for r in view["auto_applied"]], use_container_width=True)

st.subheader(f"Needs approval ({len(view['pending'])})")
approved_ids = set()
edits = {}
for r in view["pending"]:
    with st.expander(f"[{r['code']}] segment {r['tu_id']} — {r['problemname']}"):
        st.text(f"Source:  {r['source']}")
        st.text(f"Current: {r['current_target']}")
        st.caption(r["rationale"])
        proposed = r["proposed_target"] if r["proposed_target"] is not None else r["current_target"]
        new = st.text_area("Proposed target (edit if the suggestion is wrong)",
                           value=proposed, key=f"edit_{r['item_id']}")
        if st.checkbox("Approve this fix", key=f"appr_{r['item_id']}"):
            approved_ids.add(r["item_id"])
            edits[r["item_id"]] = new

with st.expander(f"Report-only — manual review ({len(view['report_only'])})"):
    st.dataframe([{"code": r["code"], "segment": r["tu_id"],
                   "problem": r["problemname"], "note": r["rationale"]}
                  for r in view["report_only"]], use_container_width=True)

st.divider()
if st.button("Apply & build corrected file", type="primary"):
    items = items_for_apply(rs, approved_ids, edits)
    try:
        fixed = apply(st.session_state["content"], items)
    except Exception as exc:
        st.error(f"Could not build a valid file (an edited target may have broken "
                 f"the XML/tags): {exc}")
    else:
        st.success(f"Applied {len(items)} fixes ({len(rs.auto_applied)} automatic "
                   f"+ {len(approved_ids)} approved).")
        st.download_button("Download corrected .mqxliff", data=fixed,
                           file_name="FIXED.mqxliff", mime="application/xml")
```

- [ ] **Step 4: Run; verify pass; full suite**

Run: `python -m pytest tests/test_streamlit_app.py -v` → PASS (2). Then `python -m pytest -q` → all green. (If `streamlit` isn't installed in the env, `pip install streamlit` first.)

- [ ] **Step 5: Manual launch check (record result)**

Run: `streamlit run streamlit_app.py` does not need to stay running in CI; for this plan, just confirm it imports cleanly:
`python -c "import streamlit_app"` → no exception (the module-level Streamlit calls are guarded; importing under non-Streamlit context may print warnings but must not raise ImportError for `qa_engine`).
> Note: `import streamlit_app` will execute Streamlit calls outside a script-run context and may emit "missing ScriptRunContext" warnings — that's expected and not a failure. The AppTest in Step 1 is the real check.

- [ ] **Step 6: Commit**

```bash
git add streamlit_app.py tests/test_streamlit_app.py
git commit -m "feat: standalone Streamlit app over qa_engine (upload/approve/edit/download)"
```
End with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 3: Final verification

- [ ] **Step 1:** `python -m pytest -q` → all green (expect ~70). Record count.
- [ ] **Step 2:** Confirm `qa_engine/` still has no `streamlit`/`fastapi` imports: `grep -rn "import streamlit\|import fastapi" qa_engine` → empty (the UI dependency lives only in `streamlit_app.py`).
- [ ] **Step 3:** No commit needed if 1–2 are clean (work already committed in Tasks 1–2).

---

## Self-Review

- **Spec §5/§6 (review UI: approve/edit/reject + auto summary):** Task 2 app renders auto-applied summary, pending approve/edit, report-only; reject = simply not approving. ✓
- **Engine/UI separation (spec §2):** all logic in `engine.items_for_apply`/`session_to_view` (Task 1, tested); `streamlit_app.py` only calls engine functions; Task 3 Step 2 asserts no UI import leaks into the engine. ✓
- **Placeholder scan:** complete code in every step. ✓
- **Type consistency:** `items_for_apply(session, approved_ids, edits)` and `session_to_view(session)` signatures match across Task 1 impl, tests, and the Task 2 app calls. `ResolvedItem`/`Resolution` reused via `dataclasses.replace`. ✓
- **Edit footgun:** a user edit that breaks tags/XML is caught by `engine.apply`'s in-memory validation; the app surfaces it as an error (Task 2 Step 3 try/except) rather than producing a broken file. Noted.
