from qa_engine.whitespace import collapse_internal_spaces


def test_collapse_internal_runs():
    assert collapse_internal_spaces("a   b    c") == "a b c"


def test_collapse_preserves_single_and_markers():
    assert collapse_internal_spaces("a b ⟦1:<g>⟧ c") == "a b ⟦1:<g>⟧ c"
    assert collapse_internal_spaces("a  ⟦1:<g>⟧  b") == "a ⟦1:<g>⟧ b"


def test_collapse_noop_when_already_single():
    assert collapse_internal_spaces("already single spaced") == "already single spaced"
