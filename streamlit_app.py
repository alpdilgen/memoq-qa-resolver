import os
import streamlit as st

from qa_engine.engine import analyze_stream, apply, session_to_view, items_for_apply
from qa_engine.aiclient import ClaudeAIClient
from qa_engine.tags import to_chips
from qa_engine.checkpoint import Checkpoint, content_key

CACHE_DIR = ".qa_cache"

st.set_page_config(page_title="memoQ QA Resolver", layout="wide")
st.title("memoQ QA Resolver")
st.caption("Every flagged segment is checked by the AI: genuine false positives are ignored, "
           "real errors are fixed, and anything the AI isn't fully sure about is left for you.")

# --- Sidebar: AI settings ---
st.sidebar.header("Settings")
use_ai = st.sidebar.checkbox("Use AI (Claude)", value=True)
default_key = ""
try:
    default_key = st.secrets.get("anthropic_api_key", "")
except Exception:
    default_key = ""
api_key = st.sidebar.text_input("Anthropic API key", value=default_key, type="password")
threshold = st.sidebar.slider("Auto-apply confidence threshold", min_value=50, max_value=100,
                              value=100, step=5,
                              help="A fix is applied automatically only when the AI's confidence "
                                   "is at least this. Below it, the fix waits for your approval.")
batch_size = st.sidebar.slider("Segments per AI call (batch size)", min_value=1, max_value=25,
                               value=12,
                               help="Higher = far fewer API calls on big files (much faster, "
                                    "resilient to timeouts). Lower if a call ever gets too large.")
st.sidebar.caption("Without a key, only deterministic fixes (whitespace, safe tag rules) run; "
                   "everything needing judgement waits for approval. Progress is checkpointed — "
                   "if the page reloads mid-run, re-run the same file to resume from where it stopped.")

uploaded = st.file_uploader("memoQ .mqxliff", type=["mqxliff"])

# Clicking Analyze records a persistent job (survives reruns) so a dropped
# connection resumes from the on-disk checkpoint instead of restarting.
if uploaded is not None and st.button("Analyze QA issues", type="primary"):
    content = uploaded.read()
    st.session_state["job"] = {
        "content": content, "key": content_key(content), "threshold": threshold,
        "batch_size": batch_size, "use_ai": use_ai, "api_key": api_key, "running": True,
    }
    st.session_state.pop("rs", None)

job = st.session_state.get("job")
if job and job.get("running"):
    ai_client = None
    if job["use_ai"] and job["api_key"]:
        import anthropic
        ai_client = ClaudeAIClient(anthropic.Anthropic(api_key=job["api_key"]))

    os.makedirs(CACHE_DIR, exist_ok=True)
    ckpt = Checkpoint(os.path.join(CACHE_DIR, job["key"] + ".json"))
    resumed = len(ckpt.all_items())
    if resumed:
        st.info(f"Resuming — {resumed} segments already done are loaded from the checkpoint.")

    bar = st.progress(0.0)
    status = st.empty()
    gen = analyze_stream(job["content"], ai_client=ai_client, glossary={},
                         threshold=job["threshold"], batch_size=job["batch_size"], checkpoint=ckpt)
    rs = None
    try:
        while True:
            p = next(gen)
            bar.progress(p.index / p.total if p.total else 1.0)
            verdict = {"fix": "✅ fixed", "ignore": "➖ ignored (false positive)",
                       "needs_approval": "🟡 needs approval"}.get(p.verdict, p.verdict)
            status.markdown(f"**{p.index}/{p.total}** · segment {p.tu_id} · "
                            f"`{', '.join(p.codes)}` · {p.problem} → {verdict}")
    except StopIteration as stop:
        rs = stop.value
    bar.progress(1.0)
    status.markdown(f"Done — checked {rs.total_issues} issues across "
                    f"{len(rs.auto_applied) + len(rs.pending)} segments.")
    st.session_state["rs"] = rs
    st.session_state["content"] = job["content"]
    job["running"] = False


def render(rs):
    view = session_to_view(rs)
    auto_fixes = [r for r in view["auto_applied"] if r["action"] != "ignore"]
    auto_ignores = [r for r in view["auto_applied"] if r["action"] == "ignore"]

    # --- Reconciliation header (issues = the one unit; every issue is accounted for) ---
    fixed_n = sum(it.issue_count for it in rs.auto_applied if it.resolution.action != "ignore")
    ignored_n = sum(it.issue_count for it in rs.auto_applied if it.resolution.action == "ignore")
    pending_n = sum(it.issue_count for it in rs.pending)
    st.info(f"**{rs.total_issues}** QA issues  =  **{fixed_n}** auto-corrected  +  "
            f"**{ignored_n}** ignored (false positive, translation kept)  +  "
            f"**{pending_n}** need your input")
    if fixed_n + ignored_n + pending_n != rs.total_issues:
        st.error("Ledger mismatch — some issues are unaccounted for. This is a bug.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Auto-corrected", fixed_n)
    c2.metric("Ignored (false positive)", ignored_n)
    c3.metric("Need your input", pending_n)

    with st.expander(f"Auto-corrected ({len(auto_fixes)} segments)"):
        st.dataframe([{"code": r["code"], "segment": r["tu_id"],
                       "before": to_chips(r["current_target"]),
                       "after": to_chips(r["proposed_target"] or "")}
                      for r in auto_fixes], use_container_width=True)

    with st.expander(f"Ignored — false positive, translation kept ({len(auto_ignores)} segments)"):
        st.dataframe([{"code": r["code"], "segment": r["tu_id"], "rationale": r["rationale"]}
                      for r in auto_ignores], use_container_width=True)

    st.subheader(f"Need your input ({len(view['pending'])} segments)")
    st.caption("For each segment pick one: **Confirm AI fix** · **Ignore (false positive)** · "
               "**Apply my edit**. Inline tags show as chips like `[<cf size=9.5>]`; in the edit box "
               "they appear as `⟦id:tag⟧` — change the wording freely but keep every `⟦…⟧` marker.")
    pending_items = {it.item_id: it for it in rs.pending}
    approved_ids = set()
    ignore_ids = set()
    edits = {}
    for r in view["pending"]:
        it = pending_items.get(r["item_id"])
        has_fix = r["proposed_target"] is not None and r["action"] == "fix"
        with st.expander(f"[{r['code']}] segment {r['tu_id']} — {r['problemname']}"):
            st.text(f"Source:   {to_chips(r['source'])}")
            st.text(f"Current:  {to_chips(r['current_target'])}")
            if has_fix:
                st.text(f"Proposed: {to_chips(r['proposed_target'])}")
            st.caption(r["rationale"])
            options = ["Leave for later"]
            if has_fix:
                options.append("Confirm AI fix")
            options += ["Ignore (false positive)", "Apply my edit"]
            choice = st.radio("Decision", options, horizontal=True, key=f"dec_{r['item_id']}")
            seed = it.proposed_tokens if it is not None else (r["proposed_target"] or "")
            new = st.text_area("Edit (keep the ⟦…⟧ tags)", value=seed, key=f"edit_{r['item_id']}")
            if choice == "Confirm AI fix":
                approved_ids.add(r["item_id"])               # apply precomputed AI target
            elif choice == "Ignore (false positive)":
                ignore_ids.add(r["item_id"])                  # mark codes ignored, keep translation
            elif choice == "Apply my edit":
                approved_ids.add(r["item_id"])
                edits[r["item_id"]] = new                      # detokenized + applied

    st.divider()
    if st.button("Apply & build corrected file", type="primary"):
        items = items_for_apply(rs, approved_ids, edits, ignore_ids)
        try:
            fixed = apply(st.session_state["content"], items)
        except Exception as exc:
            st.error(f"Could not build a valid file (an edited target may have broken the "
                     f"XML/tags): {exc}")
        else:
            applied_issues = sum(it.issue_count for it in items)
            st.success(f"Built corrected file: {applied_issues} issues resolved "
                       f"({fixed_n + ignored_n} automatic + {len(approved_ids)} approved segments).")
            st.download_button("Download corrected .mqxliff", data=fixed,
                               file_name="FIXED.mqxliff", mime="application/xml")


rs = st.session_state.get("rs")
if rs is None:
    st.info("Upload a file and click **Analyze QA issues** to begin.")
else:
    render(rs)
