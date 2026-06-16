from qa_engine.models import Resolution, ResolvedItem
from qa_engine.apply import apply_resolved_items

DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
    '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
    '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
    '<source xml:space="preserve">A;B</source>\n'
    '<target xml:space="preserve">A;B</target>\n'
    '<mq:warnings40><mq:errorwarning mq:errorwarning-code="03073" mq:errorwarning-problemname="space missing after sign" mq:errorwarning-localizationargs="x" /></mq:warnings40>\n'
    '</trans-unit></body></file></xliff>\n'
).encode("utf-8")


def test_ignore_marks_any_code_warning_ignored():
    it = ResolvedItem("g1:3073", "g1", "1", "3073", "p", "A;B", "A;B", "A;B",
                      Resolution(action="ignore", needs_approval=False, strategy="ai"))
    out = apply_resolved_items(DOC, [it]).decode("utf-8-sig")
    assert 'mq:errorwarning-ignored="errorwarning-ignored"' in out  # 3073 warning marked ignored
    assert "A;B" in out                                              # translation untouched
