from qa_engine.models import Member, Case, Decision


def test_member_roundtrip_fields():
    m = Member(
        tu_id="1",
        segmentguid="abc",
        source_text="Secure Fit",
        target_text="Asfalis",
        source_tags={},
        target_tags={},
        status="PartiallyEdited",
        tm_match=None,
        warning_keys=[("inconsistent translation", "Secure Fit\tAsfalis")],
    )
    assert m.tu_id == "1"
    assert m.warning_keys[0][0] == "inconsistent translation"


def test_case_distinct_counts():
    members = [
        Member("1", "g1", "Color box: ", "Kouti", {}, {}, "Edited", None, []),
        Member("2", "g2", "Color box:", "Kouti", {}, {}, "Edited", None, []),
    ]
    c = Case(id="c1", type="target_inconsistency", members=members,
             mechanical_diff="trailing whitespace")
    assert c.distinct_sources == {"Color box: ", "Color box:"}
    assert c.distinct_targets == {"Kouti"}


def test_decision_defaults():
    d = Decision(case_id="c1", category="false_positive",
                 rationale="sources differ only by trailing space",
                 confidence="high")
    assert d.chosen_member_id is None
    assert d.differentiated == []
