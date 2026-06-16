from pathlib import Path
from lxml import etree
from qa_engine.engine import analyze, apply

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        return {"category": "false_positive", "rationale": "ws", "confidence": "high"}


def test_apply_auto_and_approved_yields_valid_xml():
    content = FIX.read_bytes()
    rs = analyze(content, ai_client=_Fake(), glossary={})
    # approve everything pending as-is
    items = rs.auto_applied + rs.pending
    fixed = apply(content, items)
    etree.fromstring(fixed)                      # valid XML, no exception
    assert isinstance(fixed, bytes)


def test_apply_fix_writes_new_target(tmp_path):
    # craft an item that sets a target
    content = FIX.read_bytes()
    rs = analyze(content, ai_client=_Fake(), glossary={})
    # force one fix item
    from qa_engine.models import Resolution, ResolvedItem
    it = ResolvedItem("g1:x:0", "g1", "1", "3050", "p", "s", "t",
                      "ΝΕΟ", Resolution(action="fix", new_target="ΝΕΟ",
                      confidence=1.0, needs_approval=False, strategy="deterministic"))
    fixed = apply(content, [it]).decode("utf-8-sig")
    import re
    m = re.search(r'segmentguid="g1".*?<target[^>]*>(.*?)</target>', fixed, re.S)
    assert m.group(1) == "ΝΕΟ"


def test_apply_fix_beats_ignore_for_same_segment():
    from qa_engine.models import Resolution, ResolvedItem
    from qa_engine.apply import apply_resolved_items
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="el" datatype="x-memoq"><body>\n'
        '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
        '<source xml:space="preserve">X</source>\n'
        '<target xml:space="preserve">Y</target>\n'
        '<mq:warnings40>\n'
        '<mq:errorwarning mq:errorwarning-code="03101" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-localizationargs="a&#9;b" />\n'
        '</mq:warnings40>\n'
        '</trans-unit>\n'
        '</body></file></xliff>\n'
    ).encode("utf-8")
    ign = ResolvedItem("g1:3101:0", "g1", "1", "3101", "p", "X", "Y", None,
                       Resolution(action="ignore", needs_approval=False, strategy="ai"))
    fix = ResolvedItem("g1:3050:1", "g1", "1", "3050", "p", "X", "Y", "ΝΕΟ",
                       Resolution(action="fix", new_target="ΝΕΟ", needs_approval=False, strategy="deterministic"))
    # ignore listed BEFORE fix -> fix must still win
    out = apply_resolved_items(content, [ign, fix]).decode("utf-8-sig")
    assert "<target xml:space=\"preserve\">ΝΕΟ</target>" in out
    # and reversed order -> same result
    out2 = apply_resolved_items(content, [fix, ign]).decode("utf-8-sig")
    assert "ΝΕΟ" in out2
