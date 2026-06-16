from qa_engine.engine import analyze_stream, reconcile
from qa_engine.models import Progress


class _Canon:
    def resolve(self, system, user, schema):
        if "code_verdicts" in schema.get("properties", {}):
            return {"code_verdicts": [{"code": "3100", "verdict": "fix"}],
                    "fixed_target": "Acme Corp.", "confidence": 100, "rationale": "x"}
        return {"canonical_target": "Acme Corp.", "auto_apply": True,
                "confidence": "high", "rationale": "unify"}


DOC = (
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


def test_stream_yields_progress_per_segment_and_returns_session():
    events, session = [], None
    gen = analyze_stream(DOC, ai_client=_Canon())
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        session = stop.value
    assert len(events) == 2
    assert all(isinstance(e, Progress) for e in events)
    assert [e.index for e in events] == [1, 2]
    assert all(e.total == 2 for e in events)
    assert all(e.verdict in ("fix", "ignore", "needs_approval") for e in events)
    reconcile(session)
    assert session.total_issues == 2
