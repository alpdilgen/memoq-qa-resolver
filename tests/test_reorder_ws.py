from qa_engine.engine import _plan_segment
from qa_engine.models import Member, Issue

# reordered target (g-spans swapped vs source) that also has a tag-boundary space (3193)
SRC = "⟦1:<cf a>⟧X⟦2:</cf>⟧⟦3:<cf b>⟧Y⟦4:</cf>⟧"
TGT = "⟦3:<cf b>⟧Y ⟦4:</cf>⟧⟦1:<cf a>⟧X⟦2:</cf>⟧"   # tags present, reordered; extra space before ⟦4⟧
TAGS = {"1": "<x/>", "2": "<x/>", "3": "<x/>", "4": "<x/>"}


def _member():
    return Member("6", "g6", SRC, TGT, TAGS, TAGS, "C", None, [])


def _issues():
    return [Issue("02016", "changed tag order", "x", "g6", "6"),
            Issue("03193", "extra space after tag", "x", "g6", "6")]


class _FixWS:
    """AI that fixes the boundary whitespace, preserving all tags, fully confident."""
    def resolve(self, system, user, schema):
        return {"code_verdicts": [{"code": "3193", "verdict": "fix"},
                                  {"code": "2016", "verdict": "false_positive"}],
                "fixed_target": "⟦3:<cf b>⟧Y⟦4:</cf>⟧⟦1:<cf a>⟧X⟦2:</cf>⟧",  # space removed, tags kept
                "confidence": 100, "rationale": "removed extra space before tag; reorder is valid"}


def test_reordered_whitespace_routes_to_ai_and_auto_fixes():
    res = _plan_segment("g6", _member(), _issues(), _FixWS(), xseg={}, threshold=100)
    assert res.strategy == "ai"                 # not the deterministic aligner
    assert res.new_target is not None and "⟦" not in res.new_target
    assert res.needs_approval is False
    assert "2016" in res.ignore_codes           # reorder marked false positive


def test_reordered_whitespace_without_ai_goes_to_human_not_misfixed():
    res = _plan_segment("g6", _member(), _issues(), None, xseg={}, threshold=100)
    assert res.needs_approval is True           # never silently mis-aligned on a reordered segment
