from qa_engine.models import Member
from qa_engine.tagfix import plan_tag_structure


def _m(src, tgt, src_tags, tgt_tags):
    return Member("5", "g5", src, tgt, src_tags, tgt_tags, "C", None, [])


def test_2016_parity_is_false_positive():
    # same tags, reordered -> ignore 2016, no tag rewrite
    src = "⟦1:<cf 9.5>⟧A⟦2:</cf>⟧⟦3:<cf b>⟧M⟦4:</cf>⟧"
    tgt = "⟦3:<cf b>⟧M⟦4:</cf>⟧⟦1:<cf 9.5>⟧A⟦2:</cf>⟧"
    m = _m(src, tgt, {}, {})
    ign, new_xml, rem = plan_tag_structure(m, ["02016"])
    assert ign == ["2016"] and new_xml is None and rem == []


def test_2016_non_parity_goes_to_human():
    src = "⟦1:<cf 9.5>⟧A⟦2:</cf>⟧"
    tgt = "⟦1:<cf 9.5>⟧A"          # missing close -> not parity
    m = _m(src, tgt, {}, {})
    ign, new_xml, rem = plan_tag_structure(m, ["2016"])
    assert ign == [] and rem == ["2016"]


def test_2011_inserts_missing_tags_in_source_order():
    # source: ph A ph B [g]C[/g]   target missing the 2 ph that precede the g-span.
    # The re-added ph must land BEFORE the g (source order), not appended at the end.
    src = "⟦1:<ph>⟧A⟦2:<ph>⟧B⟦3:<cf c>⟧C⟦4:</cf>⟧"
    tgt = "B⟦3:<cf c>⟧C⟦4:</cf>⟧"          # missing ph 1 and 2 (both before the g-span)
    src_tags = {
        "1": '<ph id="1">&lt;mq:ch val="x" /&gt;</ph>',
        "2": '<ph id="2">&lt;mq:ch val="x" /&gt;</ph>',
        "3": '<bpt id="3" rid="1">&lt;g id="9" mmq78catalogvalue="&amp;lt;cf c&amp;gt;"&gt;</bpt>',
        "4": '<ept id="4" rid="1">&lt;/g mmq78catalogvalue="&amp;lt;/cf&amp;gt;"&gt;</ept>',
    }
    tgt_tags = {"3": src_tags["3"], "4": src_tags["4"]}
    m = _m(src, tgt, src_tags, tgt_tags)
    ign, new_xml, rem = plan_tag_structure(m, ["02011"])
    assert ign == [] and rem == [] and new_xml is not None
    # both ph re-added (count parity) AND they appear before the <g> open (order)
    assert new_xml.count("<ph") == 2
    assert new_xml.index("<ph") < new_xml.index("<bpt")   # ph before the g-span, not appended


def test_2011_missing_paired_tag_goes_to_human():
    # missing a <g> (paired bpt/ept) -> cannot auto-add safely
    src = "⟦1:<g>⟧A⟦2:</g>⟧B"
    tgt = "B"
    src_tags = {"1": '<bpt id="1" rid="1">&lt;g id="9"&gt;</bpt>', "2": '<ept id="2" rid="1">&lt;/g&gt;</ept>'}
    m = _m(src, tgt, src_tags, {})
    ign, new_xml, rem = plan_tag_structure(m, ["2011"])
    assert rem == ["2011"] and new_xml is None


def test_2015_and_2010_go_to_human():
    m = _m("⟦1:<ph>⟧", "⟦1:<ph>⟧", {}, {})
    ign, new_xml, rem = plan_tag_structure(m, ["2015", "2010"])
    assert sorted(rem) == ["2010", "2015"] and new_xml is None
