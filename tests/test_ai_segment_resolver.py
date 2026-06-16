from qa_engine.models import Issue, Member
from qa_engine.resolvers.ai_segment_resolver import resolve_segment, SEGMENT_SCHEMA


class _Fake:
    def __init__(self, payload):
        self.payload = payload
        self.last = None
    def resolve(self, system_prompt, user_content, schema):
        self.last = (system_prompt, user_content, schema)
        return self.payload


def _member(src, tgt, tags=None):
    return Member("5", "g5", src, tgt, {}, tags or {}, "Edited", None, [])


def test_auto_apply_fix():
    fake = _Fake({"verdict": "fix", "fixed_target": "Άμμος", "auto_apply": True, "confidence": "high",
                  "rationale": "distinct color"})
    issues = [Issue("3101", "inconsistent translation", "Sand\tΆμμος", "g5", "5")]
    res = resolve_segment(_member("Sand", "Σοφιστικέ"), issues, context=None, ai_client=fake)
    assert res.action == "fix" and res.new_target == "Άμμος"
    assert res.needs_approval is False and res.strategy == "ai"
    # the schema was passed, and the code description reached the prompt
    assert fake.last[2] == SEGMENT_SCHEMA
    assert "inconsistent" in fake.last[1].lower()


def test_needs_approval_when_not_auto():
    fake = _Fake({"verdict": "fix", "fixed_target": "Νέο", "auto_apply": False, "confidence": "medium",
                  "rationale": "uncertain"})
    issues = [Issue("3091", "missing term", "x", "g5", "5")]
    res = resolve_segment(_member("X", "Y"), issues, context=None, ai_client=fake)
    assert res.action == "fix" and res.needs_approval is True


def test_marker_mismatch_falls_back_to_needs_approval_report():
    # AI returned a target with a bogus marker not in the segment's tags
    fake = _Fake({"verdict": "fix", "fixed_target": "Νέο ⟦9⟧", "auto_apply": True, "confidence": "high",
                  "rationale": "x"})
    issues = [Issue("3101", "inconsistent translation", "x", "g5", "5")]
    res = resolve_segment(_member("X", "Y", tags={}), issues, context=None, ai_client=fake)
    # cannot safely detokenize -> keep as a suggestion needing human approval, never auto
    assert res.needs_approval is True


def test_false_positive_high_conf_auto_ignores():
    fake = _Fake({"verdict": "false_positive", "fixed_target": "",
                  "auto_apply": True, "confidence": "high",
                  "rationale": "';' is part of the &quot; entity; source==target; not a real error"})
    issues = [Issue("3073", "space missing after sign", ";", "g5", "5")]
    res = resolve_segment(_member("&quot;https://x", "&quot;https://x"), issues, None, fake)
    assert res.action == "ignore" and res.needs_approval is False and res.strategy == "ai"


def test_false_positive_low_conf_needs_approval():
    fake = _Fake({"verdict": "false_positive", "fixed_target": "",
                  "auto_apply": False, "confidence": "low", "rationale": "maybe"})
    res = resolve_segment(_member("X", "X"), [Issue("3100", "inconsistent", "", "g5", "5")], None, fake)
    assert res.action == "ignore" and res.needs_approval is True


def test_fix_verdict_still_fixes():
    fake = _Fake({"verdict": "fix", "fixed_target": "Άμμος", "auto_apply": True,
                  "confidence": "high", "rationale": "distinct color"})
    res = resolve_segment(_member("Sand", "Σοφιστικέ"), [Issue("3101","inc","","g5","5")], None, fake)
    assert res.action == "fix" and res.new_target == "Άμμος" and res.needs_approval is False
