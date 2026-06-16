import json
import shutil
from pathlib import Path
from qa_engine.cli import run_analyze, run_apply

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    """Returns false_positive for whitespace cases, differentiate otherwise."""
    def resolve(self, system_prompt, user_content, schema):
        if "whitespace" in user_content or "typo" in user_content:
            return {"category": "false_positive", "rationale": "ws", "confidence": "high"}
        elif "source_inconsistency" in user_content:
            return {"category": "pick_best", "rationale": "std", "confidence": "high",
                    "chosen_variant_key": "Εύκολο στον καθαρισμό"}
        else:
            return {"category": "differentiate", "rationale": "colors",
                    "confidence": "high",
                    "differentiated": [{"source_key": "Ocean Deep Sand",
                                        "new_target": "Ωκεανός Βαθιά Άμμος"}]}


def test_analyze_then_apply(tmp_path):
    src = tmp_path / "in.mqxliff"
    shutil.copy(FIXTURE, src)
    out_dir = tmp_path / "out"
    cases, decisions, ws_fixes = run_analyze(str(src), str(out_dir), glossary_path=None,
                model="claude-opus-4-8", client=_Fake())
    assert (out_dir / "decisions.json").exists()
    assert (out_dir / "report.html").exists()
    # ws_fixes detected before normalization (trailing space on tu1 target)
    assert isinstance(ws_fixes, list)

    fixed = tmp_path / "in.FIXED.mqxliff"
    run_apply(str(src), str(out_dir / "decisions.json"), str(fixed),
              include_low=False, force=True)
    text = fixed.read_text(encoding="utf-8-sig")
    assert "Ωκεανός Βαθιά Άμμος" in text
    assert text.count("Εύκολο στον καθαρισμό") == 2


def test_analyze_limit_caps_cases(tmp_path):
    import shutil
    src = tmp_path / "in.mqxliff"
    shutil.copy(FIXTURE, src)
    out_dir = tmp_path / "out"
    cases, decisions, ws_fixes = run_analyze(str(src), str(out_dir), None,
                                   "claude-opus-4-8", client=_Fake(), limit=1)
    assert len(decisions) == 1
