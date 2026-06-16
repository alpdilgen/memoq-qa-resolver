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


def test_fix_at_100_auto_applies():
    fake = _Fake({"code_verdicts": [{"code": "3073", "verdict": "fix"}],
                  "fixed_target": "a; b", "confidence": 100, "rationale": "added space"})
    issues = [Issue("3073", "space missing after sign", ";", "g5", "5")]
    res = resolve_segment(_member("a; b", "a;b"), issues, None, fake, threshold=100)
    assert res.action == "fix" and res.new_target == "a; b"
    assert res.needs_approval is False and res.strategy == "ai"
    assert fake.last[2] == SEGMENT_SCHEMA
    assert "space missing after sign" in fake.last[1].lower()


def test_fix_below_threshold_needs_approval():
    fake = _Fake({"code_verdicts": [{"code": "3091", "verdict": "fix"}],
                  "fixed_target": "Yeni", "confidence": 80, "rationale": "uncertain"})
    res = resolve_segment(_member("X", "Y"), [Issue("3091", "missing term", "x", "g5", "5")],
                          None, fake, threshold=100)
    assert res.action == "fix" and res.needs_approval is True


def test_all_false_positive_ignores():
    fake = _Fake({"code_verdicts": [{"code": "3073", "verdict": "false_positive"}],
                  "fixed_target": "&quot;https://x", "confidence": 100,
                  "rationale": "';' is inside the &quot; entity"})
    res = resolve_segment(_member("&quot;https://x", "&quot;https://x"),
                          [Issue("3073", "space missing after sign", ";", "g5", "5")],
                          None, fake)
    assert res.action == "ignore" and res.needs_approval is False
    assert res.ignore_codes == ["3073"]


def test_tag_change_forces_human_even_at_100():
    # AI dropped a tag the current target had -> parity fails -> never auto
    fake = _Fake({"code_verdicts": [{"code": "3101", "verdict": "fix"}],
                  "fixed_target": "Νέο", "confidence": 100, "rationale": "x"})
    res = resolve_segment(_member("A⟦1:<ph>⟧B", "Α⟦1:<ph>⟧Β", tags={"1": '<ph id="1">x</ph>'}),
                          [Issue("3101", "inconsistent translation", "x", "g5", "5")], None, fake)
    assert res.needs_approval is True and res.new_target is None
    assert "tag" in res.rationale.lower()


def test_marker_id_mismatch_forces_human():
    # AI kept the right count but a bogus id -> detokenize fails -> human
    fake = _Fake({"code_verdicts": [{"code": "3101", "verdict": "fix"}],
                  "fixed_target": "Νέο ⟦9:<ph>⟧", "confidence": 100, "rationale": "x"})
    res = resolve_segment(_member("A⟦1:<ph>⟧", "Α⟦1:<ph>⟧", tags={"1": '<ph id="1">x</ph>'}),
                          [Issue("3101", "inconsistent translation", "x", "g5", "5")], None, fake)
    assert res.needs_approval is True and res.new_target is None


def test_mixed_fix_and_false_positive_per_code():
    # 3073 real fix; 3100 false positive -> fix target AND ignore 3100
    fake = _Fake({"code_verdicts": [{"code": "3073", "verdict": "fix"},
                                     {"code": "3100", "verdict": "false_positive"}],
                  "fixed_target": "a; b", "confidence": 100, "rationale": "mixed"})
    issues = [Issue("3073", "space after sign", ";", "g5", "5"),
              Issue("3100", "inconsistent", "", "g5", "5")]
    res = resolve_segment(_member("a; b", "a;b"), issues, None, fake)
    assert res.action == "fix" and res.new_target == "a; b"
    assert res.ignore_codes == ["3100"] and res.needs_approval is False
