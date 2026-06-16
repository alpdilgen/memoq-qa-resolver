from pathlib import Path
from qa_engine.engine import analyze, reconcile

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fix:
    def resolve(self, s, u, sch):
        return {"verdict": "fix", "fixed_target": "X", "auto_apply": True,
                "confidence": "high", "rationale": "r"}


def test_every_issue_accounted():
    rs = analyze(FIX.read_bytes(), ai_client=_Fix(), glossary={})
    assert rs.total_issues == 5
    reconcile(rs)   # raises if fix+ignore+needs_approval != total_issues


def test_no_op_whitespace_becomes_ignore_not_skip():
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
        '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
        '<source xml:space="preserve">A</source><target xml:space="preserve">A</target>\n'
        '<mq:warnings40><mq:errorwarning mq:errorwarning-code="03110" mq:errorwarning-problemname="space at segment end" mq:errorwarning-localizationargs="x" /></mq:warnings40>\n'
        '</trans-unit></body></file></xliff>\n'
    ).encode("utf-8")
    rs = analyze(doc, ai_client=None, glossary={})
    reconcile(rs)
    assert rs.total_issues == 1
    assert len(rs.auto_applied) + len(rs.pending) == 1
    # the no-op whitespace segment is accounted as an ignore, not dropped
    item = (rs.auto_applied + rs.pending)[0]
    assert item.resolution.action == "ignore"
