from pathlib import Path
from qa_engine.parser import parse_mqxliff
from qa_engine.casebuilder import build_cases
from qa_engine.context import build_case_payload

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_payload_has_variants_and_frequency():
    members = parse_mqxliff(str(FIXTURE))
    cases = build_cases(members)
    case = [c for c in cases if c.type == "source_inconsistency"][0]
    payload = build_case_payload(case, members, glossary={})
    assert payload["type"] == "source_inconsistency"
    assert payload["mechanical_diff"]
    keys = {v["text"] for v in payload["target_variants"]}
    assert "Εύκολο στο Καθάρισμα" in keys
    assert all("count" in v for v in payload["target_variants"])


def test_payload_includes_glossary_hit():
    members = parse_mqxliff(str(FIXTURE))
    cases = build_cases(members)
    case = [c for c in cases if c.type == "source_inconsistency"][0]
    payload = build_case_payload(case, members,
                                 glossary={"easy to clean": "Εύκολο στον καθαρισμό"})
    assert payload["glossary_suggestion"] == "Εύκολο στον καθαρισμό"
