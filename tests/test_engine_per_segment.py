from pathlib import Path
from qa_engine.engine import analyze

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    # Sample fixture is all 3101: grouped segments use XSEG_SCHEMA (unchanged),
    # ungrouped ones use the new per-segment SEGMENT_SCHEMA. Dispatch on schema.
    # Both return a "needs approval" suggestion with a concrete proposed target.
    def resolve(self, system_prompt, user_content, schema):
        if "code_verdicts" in schema.get("properties", {}):
            return {"code_verdicts": [{"code": "3101", "verdict": "fix"}],
                    "fixed_target": "ΔΙΟΡΘΩΜΕΝΟ", "confidence": 80, "rationale": "fix"}
        return {"canonical_target": "ΔΙΟΡΘΩΜΕΝΟ", "auto_apply": False,
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
