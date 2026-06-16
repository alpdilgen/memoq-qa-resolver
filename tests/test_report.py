import json
from qa_engine.models import Case, Member, Decision
from qa_engine.report import write_reports


def _case_and_decision():
    members = [
        Member("1", "g1", "Color box: ", "Κουτί", {}, {}, "Edited", None,
               [("inconsistent translation", "Color box:\tΚουτί")]),
        Member("2", "g2", "Color box:", "Κουτί", {}, {}, "Edited", None,
               [("inconsistent translation", "Color box: \tΚουτί")]),
    ]
    case = Case("T1", "target_inconsistency", members,
                "differ only by leading/trailing whitespace")
    dec = Decision("T1", "false_positive",
                   "sources differ only by a trailing space; target is correct",
                   "high")
    return [case], {"T1": dec}


def test_writes_json_and_html(tmp_path):
    cases, decisions = _case_and_decision()
    write_reports(cases, decisions, str(tmp_path), ws_fixes=[
        {"tu_id": "9", "segmentguid": "g9",
         "new_target_inner": "Στρώμα:", "old_preview": "   ⟦1⟧Στρώμα:", "new_preview": "⟦1⟧Στρώμα:"}])
    data = json.loads((tmp_path / "decisions.json").read_text(encoding="utf-8"))
    assert data["decisions"]["T1"]["category"] == "false_positive"
    assert len(data["whitespace_fixes"]) == 1
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "T1" in html
    assert "trailing space" in html
    assert "whitespace" in html.lower()
    assert "⟦1⟧Στρώμα:" in html        # after-preview rendered


def test_summary_counts(tmp_path):
    cases, decisions = _case_and_decision()
    write_reports(cases, decisions, str(tmp_path))
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "false_positive: 1" in html
