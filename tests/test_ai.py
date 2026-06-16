import json
from qa_engine.ai import classify_case, DECISION_SCHEMA, build_system_prompt


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.last = None

    def resolve(self, system_prompt, user_content, schema):
        self.last = {"system": system_prompt, "user": user_content, "schema": schema}
        return self._payload


def _payload():
    return {"case_id": "T1", "type": "target_inconsistency",
            "mechanical_diff": "differ only by leading/trailing whitespace",
            "source_variants": [{"key": "Color box: ", "text": "Color box: ", "count": 1},
                                {"key": "Color box:", "text": "Color box:", "count": 1}],
            "target_variants": [{"text": "Κουτί χρώματος:", "count": 2}],
            "members": [], "glossary_suggestion": None, "tm_suggestion": None}


def test_classify_returns_decision_for_false_positive():
    fake = FakeClient({"category": "false_positive",
                       "rationale": "sources differ only by trailing space; target correct",
                       "confidence": "high"})
    d = classify_case(fake, _payload(), system_prompt="x", model="claude-opus-4-8")
    assert d.category == "false_positive"
    assert d.confidence == "high"
    assert d.case_id == "T1"


def test_classify_passes_schema_and_model():
    fake = FakeClient({"category": "false_positive", "rationale": "r", "confidence": "high"})
    classify_case(fake, _payload(), system_prompt="x", model="claude-opus-4-8")
    assert fake.last["schema"] == DECISION_SCHEMA
    assert "inconsistency" in fake.last["user"].lower()
    assert fake.last["system"] == "x"


def test_system_prompt_includes_categories_and_glossary():
    sp = build_system_prompt(glossary_text="Easy to clean = X")
    assert "false_positive" in sp and "pick_best" in sp and "differentiate" in sp
    assert "Easy to clean = X" in sp
