from pathlib import Path
from qa_engine.parser import parse_issues
from qa_engine.resolvers.inconsistency_resolver import resolve_inconsistencies

FIX = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    def resolve(self, system_prompt, user_content, schema):
        if "whitespace" in user_content or "typo" in user_content:
            return {"category": "false_positive", "rationale": "ws", "confidence": "high"}
        if "source_inconsistency" in user_content:
            return {"category": "pick_best", "rationale": "std", "confidence": "high",
                    "chosen_variant_key": "Εύκολο στον καθαρισμό"}
        return {"category": "differentiate", "rationale": "colors", "confidence": "high",
                "differentiated": [{"source_key": "Ocean Deep Sand", "new_target": "Άμμος"}]}


def test_resolve_inconsistencies_returns_resolution_per_segment():
    issues, members = parse_issues(FIX.read_bytes())
    by_guid = resolve_inconsistencies(issues, members, _Fake(), glossary={})
    # returns a dict segmentguid -> Resolution for inconsistency-affected segments
    assert isinstance(by_guid, dict)
    # false_positive -> ignore, pick_best/differentiate -> fix
    actions = {r.action for r in by_guid.values()}
    assert actions <= {"fix", "ignore", "report"}
    for r in by_guid.values():
        assert r.strategy == "ai"
        assert 0.0 <= r.confidence <= 1.0
