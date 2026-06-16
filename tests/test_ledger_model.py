from qa_engine.models import Issue, ReviewSession, ResolvedItem, Resolution


def test_issue_has_outcome_default_pending():
    i = Issue(code="3050", problemname="p", args="", segmentguid="g1", tu_id="1")
    assert i.outcome in ("fix", "ignore", "needs_approval")
    assert i.outcome == "needs_approval"


def test_resolved_item_has_issue_count_default_one():
    it = ResolvedItem(
        item_id="g1:3050:0", segmentguid="g1", tu_id="1", code="3050",
        problemname="p", source_preview="", current_target_preview="",
        proposed_target_preview=None, resolution=Resolution(action="ignore"),
    )
    assert it.issue_count == 1


def test_review_session_reconciles():
    rs = ReviewSession(source_lang="en", target_lang="tr",
                       auto_applied=[], pending=[], report_only=[], total_issues=3)
    assert rs.total_issues == 3
