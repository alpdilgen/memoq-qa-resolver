from qa_engine.models import Member, Issue
from qa_engine.resolvers.inconsistency_xseg import resolve_inconsistency_groups


class _Canon:
    def resolve(self, s, u, sch):
        # pick the form WITH the period as canonical
        return {"canonical_target": "Maxmor International Trading Ltd.",
                "auto_apply": True, "confidence": "high", "rationale": "unify"}


def _m(tid, src, tgt):
    return Member(tid, "g" + tid, src, tgt, {}, {}, "C", None,
                  [("inconsistent translation", "x")])


def test_groups_same_source_and_unifies():
    members = [
        _m("1", "Maxmor International Trading Ltd.", "Maxmor International Trading Ltd."),
        _m("2", "Maxmor International Trading Ltd.", "Maxmor International Trading Ltd"),
        _m("3", "Maxmor International Trading Ltd.", "MaxMor International Trading Ltd."),
    ]
    issues = [Issue("3100", "inconsistent", "x", m.segmentguid, m.tu_id) for m in members]
    out = resolve_inconsistency_groups(issues, {m.segmentguid: m for m in members}, _Canon())
    assert set(out) == {"g1", "g2", "g3"}
    for guid, res in out.items():
        assert res.action == "fix" and res.new_target == "Maxmor International Trading Ltd."


def test_already_consistent_group_is_left_alone():
    members = [
        _m("1", "Hello", "Merhaba"),
        _m("2", "Hello", "Merhaba"),
    ]
    issues = [Issue("3100", "inconsistent", "x", m.segmentguid, m.tu_id) for m in members]
    out = resolve_inconsistency_groups(issues, {m.segmentguid: m for m in members}, _Canon())
    assert out == {}   # single distinct target -> nothing to unify


def test_non_inconsistency_issues_ignored():
    m = _m("1", "Hello", "Merhaba")
    issues = [Issue("3050", "whitespace", "x", "g1", "1")]
    out = resolve_inconsistency_groups(issues, {"g1": m}, _Canon())
    assert out == {}
