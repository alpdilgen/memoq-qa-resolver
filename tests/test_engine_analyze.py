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
