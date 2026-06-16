from qa_engine.models import Resolution, ResolvedItem, ReviewSession
from qa_engine.engine import items_for_apply


def _pending_item():
    res = Resolution(action="fix", new_target=None, needs_approval=True, strategy="ai")
    return ResolvedItem("g1:x", "g1", "1", "3101", "p", "S", "Cur", "Cur", res,
                        issue_count=1, tags={"1": '<ph id="1">x</ph>'},
                        proposed_tokens="Eski ⟦1:<ph>⟧")


def _session(it):
    return ReviewSession("en", "tr", [], [it], [], total_issues=1)


def test_edited_tokens_detokenize_to_xml():
    it = _pending_item()
    out = items_for_apply(_session(it), {"g1:x"}, {"g1:x": "Yeni ⟦1:<ph>⟧"})
    assert len(out) == 1
    assert out[0].resolution.new_target == 'Yeni <ph id="1">x</ph>'
    assert out[0].resolution.action == "fix"


def test_unchanged_edit_keeps_original_item():
    it = _pending_item()
    out = items_for_apply(_session(it), {"g1:x"}, {"g1:x": it.proposed_tokens})
    assert out[0] is it          # untouched, applies the precomputed resolution


def test_broken_tokens_keep_original_not_corrupt():
    it = _pending_item()
    # user mangled the token id -> cannot detokenize -> keep original (no corruption)
    out = items_for_apply(_session(it), {"g1:x"}, {"g1:x": "Yeni ⟦9:<ph>⟧"})
    assert out[0] is it
