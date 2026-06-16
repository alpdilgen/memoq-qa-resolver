from pathlib import Path
from qa_engine.parser import parse_mqxliff
from qa_engine.casebuilder import build_cases, describe_diff

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_builds_three_cases():
    cases = build_cases(parse_mqxliff(str(FIXTURE)))
    types = sorted(c.type for c in cases)
    # two target_inconsistency groups (Κουτί, Ωκεανός) + one source_inconsistency (Easy to clean)
    assert types == ["source_inconsistency", "target_inconsistency", "target_inconsistency"]


def test_target_case_groups_by_target():
    cases = build_cases(parse_mqxliff(str(FIXTURE)))
    kouti = [c for c in cases
             if c.type == "target_inconsistency" and "Κουτί" in next(iter(c.distinct_targets))][0]
    assert {m.tu_id for m in kouti.members} == {"1", "2"}


def test_source_case_groups_by_source():
    cases = build_cases(parse_mqxliff(str(FIXTURE)))
    src = [c for c in cases if c.type == "source_inconsistency"][0]
    assert {m.tu_id for m in src.members} == {"5", "6"}
    assert src.distinct_targets == {"Εύκολο στο Καθάρισμα", "Εύκολο στον καθαρισμό"}


def test_describe_diff_trailing_space():
    assert "whitespace" in describe_diff(["Color box: ", "Color box:"]).lower()


def test_describe_diff_typo():
    out = describe_diff(["Blister card:", "Bliser card:"]).lower()
    assert "differ" in out or "typo" in out or "char" in out
