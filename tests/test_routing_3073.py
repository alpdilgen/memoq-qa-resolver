from qa_engine.engine import analyze

DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
    '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
    '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
    '<source xml:space="preserve">A/B</source>\n'
    '<target xml:space="preserve">A/B</target>\n'
    '<mq:warnings40>\n'
    '<mq:errorwarning mq:errorwarning-code="03073" mq:errorwarning-problemname="space missing after sign" mq:errorwarning-localizationargs="/" />\n'
    '</mq:warnings40>\n'
    '</trans-unit>\n'
    '</body></file></xliff>\n'
).encode("utf-8")


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        return {"fixed_target": "A/ B", "auto_apply": True, "confidence": "high", "rationale": "added space after sign"}


def test_3073_segment_routed_to_ai_not_skipped():
    # with an AI client, the 3073 segment is resolved by AI (auto-applied), not dropped
    rs = analyze(DOC, ai_client=_Fake(), glossary={})
    items = rs.auto_applied + rs.pending
    assert any(it.code == "03073" for it in items), "3073 segment must not be silently skipped"
    # the AI fix auto-applies
    assert any(it.code == "03073" and not it.resolution.needs_approval for it in rs.auto_applied)


def test_3073_without_ai_surfaces_as_pending_not_skipped():
    rs = analyze(DOC, ai_client=None, glossary={})
    assert any(it.code == "03073" for it in rs.pending), "must surface for manual, not be dropped"
