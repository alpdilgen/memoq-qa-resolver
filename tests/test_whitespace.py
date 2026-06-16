from qa_engine.models import Member
from qa_engine.whitespace import (
    lead_ws, trail_ws, align_whitespace, compute_ws_fixes, normalize_members,
)


def _m(tu_id, src, tgt, tags=None):
    return Member(tu_id, "g" + tu_id, src, tgt, {}, tags or {}, "Edited", None, [])


def test_edge_helpers():
    assert lead_ws("   ⟦1:<g>⟧x") == "   "
    assert trail_ws("x⟦1:<g>⟧   ") == "   "
    assert lead_ws("⟦1:<g>⟧x") == ""


def test_align_removes_tag_adjacent_spaces():
    src = "⟦1:<g>⟧⟦2:<g>⟧Perfect Size⟦3:</g>⟧⟦4:</g>⟧"
    tgt = "⟦1:<g>⟧ ⟦2:<g>⟧ Ιδανικό Μέγεθος ⟦3:</g>⟧ ⟦4:</g>⟧"
    assert align_whitespace(src, tgt) == "⟦1:<g>⟧⟦2:<g>⟧Ιδανικό Μέγεθος⟦3:</g>⟧⟦4:</g>⟧"


def test_align_keeps_source_boundary_spaces():
    src = "⟦1:<g>⟧ Perfect Size ⟦2:</g>⟧"      # source HAS a space inside the tags
    tgt = "⟦1:<g>⟧Ιδανικό Μέγεθος⟦2:</g>⟧"
    assert align_whitespace(src, tgt) == "⟦1:<g>⟧ Ιδανικό Μέγεθος ⟦2:</g>⟧"


def test_align_preserves_internal_and_edges():
    src = "⟦1:<g>⟧Mattress:⟦2:</g>⟧"
    tgt = "          ⟦1:<g>⟧Στρώμα:⟦2:</g>⟧          "   # leading+trailing edge ws
    assert align_whitespace(src, tgt) == "⟦1:<g>⟧Στρώμα:⟦2:</g>⟧"


def test_align_skips_on_marker_count_mismatch():
    src = "⟦1:<g>⟧X"
    tgt = "⟦1:<g>⟧ Υ ⟦2:</g>⟧"                 # extra marker -> cannot align
    assert align_whitespace(src, tgt) == tgt   # unchanged


def test_align_leaves_nbsp_untouched():
    src = "⟦1:<g>⟧X⟦2:</g>⟧"
    tgt = "⟦1:<g>⟧\xa0Υ\xa0⟦2:</g>⟧"           # nbsp adjacent to tags, not [ \t]
    assert align_whitespace(src, tgt) == tgt


def test_compute_fixes_shape_and_detokenize():
    tags = {"1": '<ph id="1"/>'}               # mapping keyed by token id
    members = [_m("1", "⟦1:<ph/>⟧Mattress:", "   ⟦1:<ph/>⟧Στρώμα:", tags=tags)]
    fixes = compute_ws_fixes(members)
    assert len(fixes) == 1
    f = fixes[0]
    assert f["tu_id"] == "1"
    assert f["new_target_inner"] == '<ph id="1"/>Στρώμα:'   # markers restored, ws fixed
    assert f["new_preview"] == "⟦1:<ph/>⟧Στρώμα:"


def test_normalize_members_in_place():
    members = [_m("1", "⟦1:<g>⟧⟦2:<g>⟧X⟦3:</g>⟧", "⟦1:<g>⟧ ⟦2:<g>⟧ Υ ⟦3:</g>⟧")]
    normalize_members(members)
    assert members[0].target_text == "⟦1:<g>⟧⟦2:<g>⟧Υ⟦3:</g>⟧"
