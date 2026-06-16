from qa_engine.models import Issue
from qa_engine.registry import get_resolver, STRATEGY_BY_CODE
from qa_engine.resolvers.base import ReportOnlyResolver


def _issue(code):
    return Issue(code=code, problemname="p", args="", segmentguid="g1", tu_id="1")


def test_unknown_code_falls_back_to_report_only():
    r = get_resolver(_issue("99999"))
    assert isinstance(r, ReportOnlyResolver)


def test_known_codes_have_strategies():
    # normalized lookup: both "3050" and "03050" resolve
    assert STRATEGY_BY_CODE["3050"] == "deterministic"
    assert STRATEGY_BY_CODE["3101"] == "ai"
    assert STRATEGY_BY_CODE["3161"] == "report_only"


def test_report_only_resolver_returns_report_action():
    r = ReportOnlyResolver()
    res = r.resolve(_issue("3161"), member=None, context=None)
    assert res.action == "report" and res.strategy == "report_only"
    assert res.needs_approval is True
