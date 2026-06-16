from pathlib import Path
from qa_engine.engine import analyze, session_to_view, items_for_apply

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    # Sample fixture is all 3101: grouped segments use XSEG_SCHEMA (unchanged),
    # ungrouped ones use the new per-segment SEGMENT_SCHEMA. Dispatch on schema.
    def resolve(self, system_prompt, user_content, schema):
        if "code_verdicts" in schema.get("properties", {}):
            return {"code_verdicts": [{"code": "3101", "verdict": "fix"}],
                    "fixed_target": "ΔΙΟΡΘΩΜΕΝΟ", "confidence": 80, "rationale": "test fix"}
        return {"canonical_target": "ΔΙΟΡΘΩΜΕΝΟ", "auto_apply": False,
                "confidence": "high", "rationale": "test fix"}


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
