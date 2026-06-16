from qa_engine.models import Member
from qa_engine.whitespace import (
    lead_ws, trail_ws, align_whitespace, compute_ws_fixes, normalize_members,
)


def _m(tu_id, src, tgt, tags=None):
    return Member(tu_id, "g" + tu_id, src, tgt, {}, tags or {}, "Edited", None, [])


def test_edge_helpers():
    assert lead_ws("   ⟦1⟧x") == "   "
    assert trail_ws("x⟦1⟧   ") == "   "
    assert lead_ws("⟦1⟧x") == ""


def test_align_removes_tag_adjacent_spaces():
    src = "⟦1⟧⟦2⟧Perfect Size⟦3⟧⟦4⟧"
    tgt = "⟦1⟧ ⟦2⟧ Ιδανικό Μέγεθος ⟦3⟧ ⟦4⟧"
    assert align_whitespace(src, tgt) == "⟦1⟧⟦2⟧Ιδανικό Μέγεθος⟦3⟧⟦4⟧"


def test_align_keeps_source_boundary_spaces():
    src = "⟦1⟧ Perfect Size ⟦2⟧"      # source HAS a space inside the tags
    tgt = "⟦1⟧Ιδανικό Μέγεθος⟦2⟧"
    assert align_whitespace(src, tgt) == "⟦1⟧ Ιδανικό Μέγεθος ⟦2⟧"


def test_align_preserves_internal_and_edges():
    src = "⟦1⟧Mattress:⟦2⟧"
    tgt = "          ⟦1⟧Στρώμα:⟦2⟧          "   # leading+trailing edge ws
    assert align_whitespace(src, tgt) == "⟦1⟧Στρώμα:⟦2⟧"


def test_align_skips_on_marker_count_mismatch():
    src = "⟦1⟧X"
    tgt = "⟦1⟧ Υ ⟦2⟧"                 # extra marker -> cannot align
    assert align_whitespace(src, tgt) == tgt   # unchanged


def test_align_leaves_nbsp_untouched():
    src = "⟦1⟧X⟦2⟧"
    tgt = "⟦1⟧\xa0Υ\xa0⟦2⟧"           # nbsp adjacent to tags, not [ \t]
    assert align_whitespace(src, tgt) == tgt


def test_compute_fixes_shape_and_detokenize():
    tags = {"⟦1⟧": '<ph id="1"/>'}
    members = [_m("1", "⟦1⟧Mattress:", "   ⟦1⟧Στρώμα:", tags=tags)]
    fixes = compute_ws_fixes(members)
    assert len(fixes) == 1
    f = fixes[0]
    assert f["tu_id"] == "1"
    assert f["new_target_inner"] == '<ph id="1"/>Στρώμα:'   # markers restored, ws fixed
    assert f["new_preview"] == "⟦1⟧Στρώμα:"


def test_normalize_members_in_place():
    members = [_m("1", "⟦1⟧⟦2⟧X⟦3⟧", "⟦1⟧ ⟦2⟧ Υ ⟦3⟧")]
    normalize_members(members)
    assert members[0].target_text == "⟦1⟧⟦2⟧Υ⟦3⟧"
