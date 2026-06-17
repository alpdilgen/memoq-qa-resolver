from qa_engine.models import Member, Issue
from qa_engine.resolvers.batch_resolver import resolve_segment_batch, BATCH_SCHEMA


def _m(tid, src, tgt):
    return Member(tid, "g" + tid, src, tgt, {}, {}, "C", None, [])


def _items():
    return [
        ("g1", _m("1", "a;b", "a;b"), [Issue("3073", "space after sign", ";", "g1", "1")]),
        ("g2", _m("2", "X", "Y"), [Issue("3091", "missing term", "x", "g2", "2")]),
    ]


class _Batch:
    def __init__(self, payload, record=None):
        self.payload = payload
        self.record = record
    def resolve(self, system, user, schema):
        if self.record is not None:
            self.record["schema"] = schema
            self.record["user"] = user
        return self.payload


def test_batch_returns_one_resolution_per_segment():
    rec = {}
    fake = _Batch({"segments": [
        {"segment_id": "g1", "code_verdicts": [{"code": "3073", "verdict": "false_positive"}],
         "fixed_target": "a;b", "confidence": 100, "rationale": "entity"},
        {"segment_id": "g2", "code_verdicts": [{"code": "3091", "verdict": "fix"}],
         "fixed_target": "Yeni", "confidence": 100, "rationale": "added term"},
    ]}, record=rec)
    out = resolve_segment_batch(_items(), fake, threshold=100)
    assert set(out) == {"g1", "g2"}
    assert out["g1"].action == "ignore" and out["g1"].ignore_codes == ["3073"]
    assert out["g2"].action == "fix" and out["g2"].new_target == "Yeni" and out["g2"].needs_approval is False
    assert rec["schema"] == BATCH_SCHEMA
    assert "SEGMENT g1" in rec["user"] and "SEGMENT g2" in rec["user"]   # one call, both segments


def test_omitted_segment_falls_back_to_human_not_dropped():
    fake = _Batch({"segments": [
        {"segment_id": "g1", "code_verdicts": [{"code": "3073", "verdict": "fix"}],
         "fixed_target": "a; b", "confidence": 100, "rationale": "x"},
    ]})   # g2 omitted
    out = resolve_segment_batch(_items(), fake, threshold=100)
    assert set(out) == {"g1", "g2"}
    assert out["g2"].needs_approval is True and out["g2"].new_target is None


def test_api_error_sends_all_to_human():
    class _Boom:
        def resolve(self, s, u, sch):
            raise RuntimeError("rate limit")
    out = resolve_segment_batch(_items(), _Boom(), threshold=100)
    assert set(out) == {"g1", "g2"}
    assert all(r.needs_approval for r in out.values())


def test_batch_schema_has_no_unsupported_keywords():
    forbidden = {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}

    def walk(n):
        if isinstance(n, dict):
            for k, v in n.items():
                assert k not in forbidden
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(BATCH_SCHEMA)
