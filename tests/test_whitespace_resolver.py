from qa_engine.models import Issue, Member
from qa_engine.resolvers.whitespace_resolver import WhitespaceResolver


def _member(src, tgt, tags=None):
    return Member("1", "g1", src, tgt, {}, tags or {}, "Edited", None, [])


def test_resolves_tag_adjacent_space_as_auto_fix():
    m = _member("⟦1:<g>⟧⟦2:<g>⟧Perfect Size⟦3:</g>⟧", "⟦1:<g>⟧ ⟦2:<g>⟧ Ιδανικό ⟦3:</g>⟧", tags={})
    r = WhitespaceResolver().resolve(Issue("3193", "extra space after tag", "", "g1", "1"), m, None)
    assert r.action == "fix"
    assert r.strategy == "deterministic"
    assert r.needs_approval is False and r.confidence == 1.0
    # new_target is the realigned, detokenized raw inner (no tag-adjacent spaces)
    assert r.new_target == "Ιδανικό"  # tags map empty -> markers dropped in this unit test


def test_no_change_returns_report():
    m = _member("⟦1:<g>⟧X⟦2:</g>⟧", "⟦1:<g>⟧Υ⟦2:</g>⟧")
    r = WhitespaceResolver().resolve(Issue("3050", "multiple consecutive whitespaces", "", "g1", "1"), m, None)
    assert r.action == "report"   # nothing to fix (already aligned) -> informational
