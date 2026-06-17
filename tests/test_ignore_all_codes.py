from qa_engine.engine import analyze, reconcile


def _doc():
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
        # seg 1: ONLY 3050 (would normally be deterministically collapsed)
        '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">'
        '<source xml:space="preserve">a b</source><target xml:space="preserve">a  b</target>'
        '<mq:warnings40><mq:errorwarning mq:errorwarning-code="03050" mq:errorwarning-problemname="multiple whitespace" mq:errorwarning-localizationargs="x" /></mq:warnings40>'
        '</trans-unit>\n'
        # seg 2: 3050 + 3091 (mixed)
        '<trans-unit id="2" mq:status="C" mq:segmentguid="g2">'
        '<source xml:space="preserve">term</source><target xml:space="preserve">x  y</target>'
        '<mq:warnings40>'
        '<mq:errorwarning mq:errorwarning-code="03050" mq:errorwarning-problemname="multiple whitespace" mq:errorwarning-localizationargs="x" />'
        '<mq:errorwarning mq:errorwarning-code="03091" mq:errorwarning-problemname="missing term" mq:errorwarning-localizationargs="t" />'
        '</mq:warnings40></trans-unit>\n'
        '</body></file></xliff>\n'
    ).encode("utf-8")


class _Boom:
    def resolve(self, s, u, sch):
        raise AssertionError("AI must not be called for a pure ignore-all segment")


class _FixTerm:
    def resolve(self, s, u, sch):
        if "segments" in sch.get("properties", {}):
            import re
            ids = re.findall(r"=== SEGMENT (\S+) ===", u)
            return {"segments": [{"segment_id": g, "code_verdicts": [{"code": "3091", "verdict": "fix"}],
                                  "fixed_target": "FIXED", "confidence": 100, "rationale": "r"} for g in ids]}
        return {"code_verdicts": [{"code": "3091", "verdict": "fix"}],
                "fixed_target": "FIXED", "confidence": 100, "rationale": "r"}


def test_ignore_all_code_marks_ignored_no_fix_no_ai():
    # 3050 bulk-ignored: seg1 (only 3050) must NOT be collapsed and must NOT call AI
    rs = analyze(_doc(), ai_client=_Boom(), glossary={}, ignore_all_codes={"3050"})
    reconcile(rs)
    g1 = next(it for it in rs.auto_applied + rs.pending if it.segmentguid == "g1")
    assert g1.resolution.action == "ignore"
    assert g1.resolution.new_target is None          # translation untouched (NOT collapsed)
    assert "3050" in g1.resolution.ignore_codes


def test_ignore_all_on_mixed_segment_still_fixes_other_codes():
    # seg2: 3050 ignored, 3091 still resolved by the AI
    rs = analyze(_doc(), ai_client=_FixTerm(), glossary={}, batch_size=5, ignore_all_codes={"3050"})
    reconcile(rs)
    g2 = next(it for it in rs.auto_applied + rs.pending if it.segmentguid == "g2")
    assert g2.resolution.action == "fix"
    assert g2.resolution.new_target == "FIXED"        # 3091 fixed
    assert "3050" in g2.resolution.ignore_codes       # 3050 bulk-ignored alongside
    assert g2.issue_count == 2                         # both codes accounted
