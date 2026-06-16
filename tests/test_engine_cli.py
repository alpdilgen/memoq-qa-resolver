import json
from pathlib import Path
from qa_engine.engine_cli import run_qa_analyze

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


def test_qa_analyze_writes_session_json(tmp_path):
    out = tmp_path / "session.json"
    summary = run_qa_analyze(str(FIX), str(out), ai_client=_Fake(), glossary_path=None)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "auto_applied" in data and "pending" in data and "report_only" in data
    assert summary["counts"]["auto_applied"] == len(data["auto_applied"])
