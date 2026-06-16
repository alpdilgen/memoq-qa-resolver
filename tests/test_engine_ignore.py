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
    # New per-segment schema: verdict false_positive at confidence 100 -> auto-ignore.
    def resolve(self, s, u, sch):
        return {"code_verdicts": [{"code": "3073", "verdict": "false_positive"}],
                "fixed_target": "A;B", "confidence": 100,
                "rationale": "entity, not a real error"}


class _DropsTag:
    # Verdict "fix" at confidence 100, but the fixed_target DROPS the segment's
    # inline tag -> violates the tag-parity guard -> resolver forces needs_approval.
    def resolve(self, s, u, sch):
        return {"code_verdicts": [{"code": "3073", "verdict": "fix"}],
                "fixed_target": "Νεο", "confidence": 100, "rationale": "fix"}


def test_high_conf_false_positive_goes_to_auto_ignore():
    rs = analyze(_doc("03073", "space missing after sign", "A;B", "A;B"), ai_client=_FP(), glossary={})
    assert len(rs.auto_applied) == 1
    assert rs.auto_applied[0].resolution.action == "ignore"


def test_tag_dropping_fix_never_auto_even_at_full_confidence():
    # Intent revised: the blanket "risky codes never auto" rule is GONE (tag-structure
    # codes are now handled deterministically). The NEW safety net: a content-code fix
    # whose proposed target changes the segment's inline-tag multiset (here, DROPS the
    # ⟦1:..⟧ tag) violates the count-parity guard and is forced to needs_approval at
    # ANY confidence -- the resolver never auto-applies a tag-altering edit.
    tgt = 'Α<ph id="1">x</ph>Β'
    rs = analyze(_doc("03073", "space missing after sign", "AxB", tgt),
                 ai_client=_DropsTag(), glossary={})
    assert len(rs.auto_applied) == 0 and len(rs.pending) == 1
    res = rs.pending[0].resolution
    assert res.needs_approval is True and res.new_target is None
    assert "tag" in res.rationale.lower()
