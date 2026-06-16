from qa_engine.engine import analyze, reconcile


class _Canon:
    """Always unifies to the period-terminated brand form, auto-apply."""
    def resolve(self, system, user, schema):
        return {"canonical_target": "Acme Corp.", "auto_apply": True,
                "confidence": "high", "rationale": "unify to source-faithful form"}


def _doc():
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
        '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
        '<source xml:space="preserve">Acme Corp.</source><target xml:space="preserve">Acme Corp.</target>\n'
        '<mq:warnings40><mq:errorwarning mq:errorwarning-code="03100" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-localizationargs="x" /></mq:warnings40>\n'
        '</trans-unit>\n'
        '<trans-unit id="2" mq:status="C" mq:segmentguid="g2">\n'
        '<source xml:space="preserve">Acme Corp.</source><target xml:space="preserve">Acme Corp</target>\n'
        '<mq:warnings40><mq:errorwarning mq:errorwarning-code="03100" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-localizationargs="x" /></mq:warnings40>\n'
        '</trans-unit></body></file></xliff>\n'
    ).encode("utf-8")


def test_cross_segment_unifies_both_to_canonical():
    rs = analyze(_doc(), ai_client=_Canon(), glossary={})
    reconcile(rs)
    assert rs.total_issues == 2
    items = rs.auto_applied + rs.pending
    targets = {it.proposed_target_preview for it in items}
    assert targets == {"Acme Corp."}          # both segments unified
    assert all(it.resolution.action == "fix" for it in items)
