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

if rs is not None:
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
