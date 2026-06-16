"""Guard against re-introducing JSON-schema keywords the Claude structured-output
API rejects (it 400s on integer minimum/maximum, string min/maxLength, etc.)."""
from qa_engine.resolvers.ai_segment_resolver import SEGMENT_SCHEMA, resolve_segment
from qa_engine.resolvers.inconsistency_xseg import XSEG_SCHEMA
from qa_engine.models import Member, Issue

_FORBIDDEN = {"minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems", "maxItems"}


def _walk(node):
    if isinstance(node, dict):
        for k, v in node.items():
            assert k not in _FORBIDDEN, f"unsupported schema keyword: {k}"
            _walk(v)
    elif isinstance(node, list):
        for v in node:
            _walk(v)


def test_segment_schema_has_no_unsupported_keywords():
    _walk(SEGMENT_SCHEMA)


def test_xseg_schema_has_no_unsupported_keywords():
    _walk(XSEG_SCHEMA)


class _OverConfident:
    def resolve(self, s, u, sch):
        return {"code_verdicts": [{"code": "3073", "verdict": "fix"}],
                "fixed_target": "a; b", "confidence": 250, "rationale": "x"}  # out of range


def test_confidence_is_clamped():
    m = Member("5", "g5", "a; b", "a;b", {}, {}, "C", None, [])
    res = resolve_segment(m, [Issue("3073", "p", ";", "g5", "5")], None, _OverConfident(), threshold=100)
    assert 0.0 <= res.confidence <= 1.0
    assert res.needs_approval is False     # 250 -> clamped to 100 -> auto at threshold 100
