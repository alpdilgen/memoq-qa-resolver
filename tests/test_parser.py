from pathlib import Path
from qa_engine.parser import parse_mqxliff

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_parse_returns_all_trans_units():
    units = parse_mqxliff(str(FIXTURE))
    assert len(units) == 6
    assert units[0].tu_id == "1"
    assert units[0].segmentguid == "g1"


def test_parse_extracts_source_and_target_text():
    units = parse_mqxliff(str(FIXTURE))
    assert units[0].source_text == "Color box: "
    assert units[0].target_text == "Κουτί χρώματος:"


def test_parse_extracts_warnings():
    units = parse_mqxliff(str(FIXTURE))
    pn, args = units[0].warning_keys[0]
    assert pn == "inconsistent translation"
    assert "Κουτί χρώματος:" in args
    assert units[5].warning_keys == []        # tu 6 has no warnings


def test_inner_xml_preserves_inline_tag(tmp_path):
    from qa_engine.tags import detokenize
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="el" datatype="x-memoq"><body>\n'
        '<trans-unit id="1" mq:segmentguid="g1">\n'
        '<source xml:space="preserve">A<ph id="1">x</ph>B</source>\n'
        '<target xml:space="preserve">Α<ph id="1">x</ph>Β</target>\n'
        '</trans-unit>\n'
        '</body></file></xliff>\n'
    )
    p = tmp_path / "t.mqxliff"
    p.write_text(xml, encoding="utf-8")
    m = parse_mqxliff(str(p))[0]
    # tokenized text round-trips back to the EXACT original inner XML
    assert detokenize(m.source_text, m.source_tags) == 'A<ph id="1">x</ph>B'
    assert detokenize(m.target_text, m.target_tags) == 'Α<ph id="1">x</ph>Β'
    # no doubled tail, no injected namespace
    assert "BB" not in detokenize(m.source_text, m.source_tags)
    assert "xmlns" not in "".join(m.source_tags.values())


def test_inner_xml_escapes_ampersand_and_lt_gt(tmp_path):
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="el" datatype="x-memoq"><body>\n'
        '<trans-unit id="1" mq:segmentguid="g1">\n'
        '<source xml:space="preserve">Rattle &amp; teether</source>\n'
        '<target xml:space="preserve">Κουδουνίστρα &amp; μασητικό &amp;bull; x</target>\n'
        '</trans-unit>\n'
        '</body></file></xliff>\n'
    )
    p = tmp_path / "t.mqxliff"; p.write_text(xml, encoding="utf-8")
    m = parse_mqxliff(str(p))[0]
    # stored tokenized text must be XML-escaped (so it can be written back validly)
    assert "&amp;" in m.target_text and "&bull;" not in m.target_text.replace("&amp;bull;", "")
    # and re-wrapping it in a target element must be parseable
    from lxml import etree
    etree.fromstring(("<target>" + m.target_text + "</target>").encode("utf-8"))
