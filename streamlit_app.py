import streamlit as st

from qa_engine.engine import analyze, apply, session_to_view, items_for_apply
from qa_engine.aiclient import ClaudeAIClient

st.set_page_config(page_title="memoQ QA Resolver", layout="wide")
st.title("memoQ QA Resolver")
st.caption("The AI checks each flagged segment and either fixes it automatically "
           "or proposes a fix for you to approve or edit.")

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
    auto_fixes = [r for r in view["auto_applied"] if r["action"] != "ignore"]
    auto_ignores = [r for r in view["auto_applied"] if r["action"] == "ignore"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Auto-fixed", len(auto_fixes))
    c2.metric("Marked false-positive", len(auto_ignores))
    c3.metric("Needs your approval", len(view["pending"]))

    with st.expander(f"Auto-applied fixes ({len(auto_fixes)})"):
        st.dataframe([{"code": r["code"], "segment": r["tu_id"],
                       "before": r["current_target"], "after": r["proposed_target"]}
                      for r in auto_fixes], use_container_width=True)

    with st.expander(f"False-positive (ignored) — translation kept, flag silenced ({len(auto_ignores)})"):
        st.dataframe([{"code": r["code"], "segment": r["tu_id"], "rationale": r["rationale"]}
                      for r in auto_ignores], use_container_width=True)

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
