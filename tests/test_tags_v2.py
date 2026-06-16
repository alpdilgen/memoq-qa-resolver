from qa_engine.tags import tokenize, detokenize, markers_in, tag_label

PH = '<ph id="2">&lt;x id="63" mmq78catalogvalue="&amp;lt;cf size=9.5&amp;gt;" mmq78shortcatalogvalue="&amp;lt;cf size=9.5&amp;gt;" /&gt;</ph>'
STRONG = '<x id="34" mmq78catalogvalue="&lt;/strong&gt;" mmq78shortcatalogvalue="&lt;/strong&gt;" />'


def test_tag_label_from_catalog():
    assert tag_label(PH) == "<cf size=9.5>"
    assert tag_label(STRONG) == "</strong>"


def test_tag_label_fallback_to_name():
    assert tag_label('<g id="2">') == "<g>"
    assert tag_label("</g>") == "</g>"
    assert tag_label('<x id="9"/>') == "<x/>"


def test_token_is_readable_and_roundtrips():
    text = f"A{PH}B"
    toks, mapping = tokenize(text)
    assert "⟦1:<cf size=9.5>⟧" in toks         # readable id+label
    assert "<ph" not in toks
    assert detokenize(toks, mapping) == text    # exact round-trip by id


def test_detokenize_by_id_ignores_label_edits():
    text = f"A{STRONG}B"
    toks, mapping = tokenize(text)             # ⟦1:</strong>⟧
    edited = toks.replace("</strong>", "BROKEN")   # AI mangled the label, kept the id
    assert detokenize(edited, mapping) == text      # still restores by id


def test_detokenize_rejects_unknown_id():
    text = f"A{STRONG}B"
    toks, mapping = tokenize(text)
    import pytest
    with pytest.raises(ValueError):
        detokenize(toks + "⟦9:x⟧", mapping)        # id 9 not in mapping


def test_markers_in_returns_ids():
    text = f"{PH}{STRONG}"
    toks, mapping = tokenize(text)
    assert markers_in(toks) == set(mapping.keys())
