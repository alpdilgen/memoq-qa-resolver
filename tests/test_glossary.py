from qa_engine.glossary import load_glossary, lookup


def test_load_and_lookup(tmp_path):
    p = tmp_path / "gloss.tsv"
    p.write_text("Easy to clean\tΕύκολο στον καθαρισμό\nPremium\tPremium\n",
                 encoding="utf-8")
    g = load_glossary(str(p))
    assert lookup(g, "easy to clean") == "Εύκολο στον καθαρισμό"
    assert lookup(g, "missing") is None


def test_load_none_returns_empty():
    g = load_glossary(None)
    assert g == {}
