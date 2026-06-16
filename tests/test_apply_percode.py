from qa_engine.models import Resolution, ResolvedItem
from qa_engine.apply import apply_resolved_items

DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
    '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
    '<trans-unit id="5" mq:status="C" mq:segmentguid="g5">\n'
    '<source xml:space="preserve">A B</source><target xml:space="preserve">A  B</target>\n'
    '<mq:warnings40>\n'
    '<mq:errorwarning mq:errorwarning-code="03190" mq:errorwarning-problemname="missing space before tag" mq:errorwarning-localizationargs="x" />\n'
    '<mq:errorwarning mq:errorwarning-code="02016" mq:errorwarning-problemname="changed tag order" mq:errorwarning-localizationargs="x" />\n'
    '</mq:warnings40>\n'
    '</trans-unit></body></file></xliff>\n'
).encode("utf-8")


def test_fix_target_and_ignore_one_code_together():
    # 3190 -> fix target ("A  B" -> "A B"); 2016 -> false positive -> ignore that code only
    it = ResolvedItem("g5:mix", "g5", "5", "03190", "p", "A B", "A  B", "A B",
                      Resolution(action="fix", new_target="A B", needs_approval=False,
                                 strategy="ai", ignore_codes=["2016"]))
    out = apply_resolved_items(DOC, [it]).decode("utf-8-sig")
    assert "<target xml:space=\"preserve\">A B</target>" in out          # target rewritten
    # 2016 errorwarning marked ignored, 3190 NOT (it was actually fixed)
    import re
    ew2016 = re.search(r'<mq:errorwarning[^>]*02016[^>]*/>', out).group(0)
    ew3190 = re.search(r'<mq:errorwarning[^>]*03190[^>]*/>', out).group(0)
    assert "errorwarning-ignored" in ew2016
    assert "errorwarning-ignored" not in ew3190
