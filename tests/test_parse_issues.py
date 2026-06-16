from pathlib import Path
from qa_engine.parser import parse_issues, parse_languages

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_parse_languages():
    src, tgt = parse_languages(FIX.read_bytes())
    assert src == "en" and tgt == "el"


def test_parse_issues_returns_issue_per_warning():
    issues, members = parse_issues(FIX.read_bytes())
    # fixture has 5 inconsistency warnings (tu1-5) -> 5 issues
    assert len(issues) == 5
    codes = {i.code for i in issues}
    assert "03101" in codes or "3101" in codes
    # members keyed by segmentguid
    assert "g1" in members and members["g1"].tu_id == "1"


def test_issue_has_segment_link():
    issues, members = parse_issues(FIX.read_bytes())
    i = issues[0]
    assert i.segmentguid in members
