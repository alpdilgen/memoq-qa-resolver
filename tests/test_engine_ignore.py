from qa_engine.engine import analyze

def _doc(code, problemname, src, tgt):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
        f'<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
        f'<source xml:space="preserve">{src}</source>\n'
        f'<target xml:space="preserve">{tgt}</target>\n'
        f'<mq:warnings40><mq:errorwarning mq:errorwarning-code="{code}" mq:errorwarning-problemname="{problemname}" mq:errorwarning-localizationargs="x" /></mq:warnings40>\n'
        '</trans-unit></body></file></xliff>\n'
    ).encode("utf-8")


class _FP:
    def resolve(self, s, u, sch):
        return {"verdict": "false_positive", "fixed_target": "", "auto_apply": True,
                "confidence": "high", "rationale": "entity, not a real error"}


class _Fix:
    def resolve(self, s, u, sch):
        return {"verdict": "fix", "fixed_target": "X", "auto_apply": True,
                "confidence": "high", "rationale": "fix"}


def test_high_conf_false_positive_goes_to_auto_ignore():
    rs = analyze(_doc("03073", "space missing after sign", "A;B", "A;B"), ai_client=_FP(), glossary={})
    assert len(rs.auto_applied) == 1
    assert rs.auto_applied[0].resolution.action == "ignore"


def test_risky_code_never_auto_even_if_ai_says_so():
    # 2016 is risky -> forced to pending regardless of auto_apply=True
    rs = analyze(_doc("02016", "changed tag order", "A", "B"), ai_client=_Fix(), glossary={})
    assert len(rs.auto_applied) == 0 and len(rs.pending) == 1
