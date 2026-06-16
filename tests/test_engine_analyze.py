from pathlib import Path
from qa_engine.engine import analyze

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    # The sample fixture's segments are all 3101 (inconsistency). Grouped ones go
    # through the cross-segment resolver (XSEG_SCHEMA, unchanged); ungrouped ones
    # (distinct source) fall through to the per-segment resolver (SEGMENT_SCHEMA,
    # new shape). Dispatch on the schema so one fake serves both. Both return a
    # "needs approval" suggestion to keep this test's intent (pending, not auto).
    def resolve(self, system_prompt, user_content, schema):
        if "code_verdicts" in schema.get("properties", {}):
            return {"code_verdicts": [{"code": "3101", "verdict": "fix"}],
                    "fixed_target": "ΔΙΟΡΘΩΜΕΝΟ", "confidence": 80, "rationale": "test fix"}
        return {"canonical_target": "ΔΙΟΡΘΩΜΕΝΟ", "auto_apply": False,
                "confidence": "high", "rationale": "test fix"}


def test_analyze_returns_review_session():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    assert rs.source_lang == "en" and rs.target_lang == "el"
    # report_only is always empty in new model
    assert len(rs.report_only) == 0
    # every bucket holds ResolvedItem objects with item_id + resolution
    for bucket in (rs.auto_applied, rs.pending):
        for it in bucket:
            assert it.item_id and it.resolution is not None
    # auto_applied items must not need approval
    assert all(it.resolution.needs_approval is False for it in rs.auto_applied)
    # pending items must need approval
    assert all(it.resolution.needs_approval is True for it in rs.pending)


def test_analyze_strategies_are_deterministic_or_ai():
    rs = analyze(FIX.read_bytes(), ai_client=_Fake(), glossary={})
    all_items = rs.auto_applied + rs.pending
    for it in all_items:
        assert it.resolution.strategy in ("deterministic", "ai"), \
            f"Unexpected strategy: {it.resolution.strategy} on item {it.item_id}"


def test_analyze_no_ai_surfaces_pending_not_dropped():
    rs = analyze(FIX.read_bytes(), ai_client=None, glossary={})
    assert len(rs.report_only) == 0
    # judgment codes (like 3101) must appear as pending, not silently dropped
    assert len(rs.pending) >= 1
    for it in rs.pending:
        assert it.resolution.strategy == "ai"
        assert it.resolution.needs_approval is True
