from qa_engine.models import Member
from qa_engine.tagfix import plan_tag_structure


def _m(src, tgt, src_tags, tgt_tags):
    return Member("5", "g5", src, tgt, src_tags, tgt_tags, "C", None, [])


def test_2016_parity_is_false_positive():
    # same tags, reordered -> ignore 2016, no additions
    src = "⟦1:<cf 9.5>⟧A⟦2:</cf>⟧⟦3:<cf b>⟧M⟦4:</cf>⟧"
    tgt = "⟦3:<cf b>⟧M⟦4:</cf>⟧⟦1:<cf 9.5>⟧A⟦2:</cf>⟧"
    m = _m(src, tgt, {}, {})
    ign, adds, rem = plan_tag_structure(m, ["02016"])
    assert ign == ["2016"] and adds == [] and rem == []


def test_2016_non_parity_goes_to_human():
    src = "⟦1:<cf 9.5>⟧A⟦2:</cf>⟧"
    tgt = "⟦1:<cf 9.5>⟧A"          # missing close -> not parity
    m = _m(src, tgt, {}, {})
    ign, adds, rem = plan_tag_structure(m, ["2016"])
    assert ign == [] and rem == ["2016"]


def test_2011_missing_self_contained_reaches_parity():
    # source has 4 ph line-breaks, target has 2 -> add 2, renumbered to high ids
    src = "⟦1:<ph>⟧A⟦2:<ph>⟧B⟦3:<ph>⟧C⟦4:<ph>⟧"
    tgt = "⟦1:<ph>⟧A⟦2:<ph>⟧B"
    src_tags = {str(i): f'<ph id="{i}">&lt;mq:ch val="x" /&gt;</ph>' for i in (1, 2, 3, 4)}
    m = _m(src, tgt, src_tags, {"1": src_tags["1"], "2": src_tags["2"]})
    ign, adds, rem = plan_tag_structure(m, ["02011"])
    assert ign == [] and rem == []
    assert len(adds) == 2                       # count parity restored
    assert all("<ph" in a for a in adds)
    assert all('id="900' in a for a in adds)    # renumbered to unused ids (9001, 9002)


def test_2011_missing_paired_tag_goes_to_human():
    # missing a <g> (paired bpt/ept) -> cannot auto-add safely
    src = "⟦1:<g>⟧A⟦2:</g>⟧B"
    tgt = "B"
    src_tags = {"1": '<bpt id="1" rid="1">&lt;g id="9"&gt;</bpt>', "2": '<ept id="2" rid="1">&lt;/g&gt;</ept>'}
    m = _m(src, tgt, src_tags, {})
    ign, adds, rem = plan_tag_structure(m, ["2011"])
    assert rem == ["2011"] and adds == []


def test_2015_and_2010_go_to_human():
    m = _m("⟦1:<ph>⟧", "⟦1:<ph>⟧", {}, {})
    ign, adds, rem = plan_tag_structure(m, ["2015", "2010"])
    assert sorted(rem) == ["2010", "2015"] and adds == []
