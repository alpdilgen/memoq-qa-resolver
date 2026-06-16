from qa_engine.models import Member, Issue
from qa_engine.resolvers.inconsistency_xseg import resolve_inconsistency_groups, _norm_source


class _Canon:
    def resolve(self, s, u, sch):
        return {"canonical_target": "Maxmor International Trading Ltd.",
                "auto_apply": True, "confidence": "high", "rationale": "unify"}


def _m(tid, src, tgt):
    return Member(tid, "g" + tid, src, tgt, {}, {}, "C", None, [("inconsistent", "x")])


def test_norm_source_casefolds_and_strips_trailing_punct():
    assert _norm_source("Maxmor International Trading Ltd.") == _norm_source("MaxMor International Trading Ltd")
    assert _norm_source("Hello") != _norm_source("Goodbye")


def test_cross_casing_brand_occurrences_group_and_unify():
    # sources differ only by casing / trailing period -> must still group
    members = [
        _m("1", "Maxmor International Trading Ltd.", "Maxmor International Trading Ltd."),
        _m("2", "MaxMor International Trading Ltd", "MaxMor International Trading Ltd"),
        _m("3", "Maxmor International Trading Ltd", "Maxmor International Trading Ltd"),
    ]
    issues = [Issue("3100", "inconsistent", "x", m.segmentguid, m.tu_id) for m in members]
    out = resolve_inconsistency_groups(issues, {m.segmentguid: m for m in members}, _Canon())
    assert set(out) == {"g1", "g2", "g3"}                 # all three grouped despite differing sources
    for res in out.values():
        assert res.action == "fix" and res.new_target == "Maxmor International Trading Ltd."


def test_truly_different_sources_do_not_group():
    members = [_m("1", "Apple", "Elma"), _m("2", "Orange", "Portakal")]
    issues = [Issue("3100", "inconsistent", "x", m.segmentguid, m.tu_id) for m in members]
    out = resolve_inconsistency_groups(issues, {m.segmentguid: m for m in members}, _Canon())
    assert out == {}   # distinct sources, each a singleton group -> nothing to unify
