from qa_engine.tags import tokenize, detokenize

PH = '<ph id="1">&lt;x id=&quot;34&quot; /&gt;</ph>'


def test_tokenize_ph_is_opaque_marker():
    text = f"Asfalis Efarmogi{PH}"
    toks, mapping = tokenize(text)
    assert "Asfalis Efarmogi" in toks
    assert "<ph" not in toks                  # tag hidden
    assert len(mapping) == 1
    assert detokenize(toks, mapping) == text  # exact round-trip


def test_tokenize_self_closing_and_paired_g():
    text = 'A<x id="5"/>B<g id="2">mid</g>C'
    toks, mapping = tokenize(text)
    assert "<x" not in toks and "<g" not in toks
    assert "mid" in toks                      # paired g content stays visible
    assert detokenize(toks, mapping) == text


def test_detokenize_rejects_missing_marker():
    text = f"X{PH}"
    toks, mapping = tokenize(text)
    broken = toks.replace("⟦", "")            # corrupt marker
    import pytest
    with pytest.raises(ValueError):
        detokenize(broken, mapping)


def test_marker_multiset_helper():
    from qa_engine.tags import markers_in
    text = f"A{PH}B<x id=\"5\"/>"
    toks, mapping = tokenize(text)
    assert markers_in(toks) == set(mapping.keys())


def test_tokenize_bpt_ept_opaque_and_roundtrip():
    text = ('<bpt id="1" rid="1">&lt;g id=&quot;62&quot;&gt;</bpt>'
            'All-Weather Protection'
            '<ept id="3" rid="1">&lt;/g&gt;</ept>')
    toks, mapping = tokenize(text)
    assert "<bpt" not in toks and "<ept" not in toks      # hidden
    assert "All-Weather Protection" in toks               # text visible
    assert len(mapping) == 2
    assert detokenize(toks, mapping) == text              # exact round-trip
