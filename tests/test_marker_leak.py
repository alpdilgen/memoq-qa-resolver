from qa_engine.models import Resolution, ResolvedItem
from qa_engine.apply import apply_resolved_items
from qa_engine.engine import analyze

DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
    '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
    '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
    '<source xml:space="preserve">A<ph id="1">x</ph>B</source>\n'
    '<target xml:space="preserve">Α<ph id="1">x</ph>Β</target>\n'
    '<mq:warnings40>\n'
    '<mq:errorwarning mq:errorwarning-code="03101" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-localizationargs="a&#9;b" />\n'
    '</mq:warnings40>\n'
    '</trans-unit>\n'
    '</body></file></xliff>\n'
).encode("utf-8")


def test_apply_never_writes_marker_text():
    it = ResolvedItem("g1:x", "g1", "1", "3101", "p", "A x B", "Α x Β",
                      "Α ⟦1⟧ Β",
                      Resolution(action="fix", new_target="Α ⟦1⟧ Β",
                                 needs_approval=False, strategy="ai"))
    out = apply_resolved_items(DOC, [it]).decode("utf-8-sig")
    assert "⟦" not in out and "⟧" not in out          # no markers written
    assert '<ph id="1">x</ph>' in out                            # original tag preserved


def test_analyze_previews_have_no_markers():
    rs = analyze(DOC, ai_client=None, glossary={})
    items = rs.auto_applied + rs.pending
    assert items
    for it in items:
        assert "⟦" not in it.source_preview
        assert "⟦" not in it.current_target_preview
        assert "⟦" not in (it.proposed_target_preview or "")
