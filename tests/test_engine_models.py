from qa_engine.models import Issue, Resolution, ResolvedItem, ReviewSession


def test_issue_fields():
    i = Issue(code="3050", problemname="multiple consecutive whitespaces",
              args="x", segmentguid="g1", tu_id="1")
    assert i.code == "3050" and i.segmentguid == "g1"


def test_resolution_defaults():
    r = Resolution(action="report")
    assert r.new_target is None and r.confidence == 0.0
    assert r.needs_approval is True and r.strategy == ""


def test_resolved_item_holds_resolution():
    r = Resolution(action="fix", new_target="X", confidence=1.0,
                   needs_approval=False, strategy="deterministic")
    it = ResolvedItem(item_id="g1:3050:0", segmentguid="g1", tu_id="1",
                      code="3050", problemname="p", source_preview="s",
                      current_target_preview="t", proposed_target_preview="X",
                      resolution=r)
    assert it.resolution.action == "fix" and it.item_id == "g1:3050:0"


def test_review_session_buckets():
    rs = ReviewSession(source_lang="en", target_lang="el",
                       auto_applied=[], pending=[], report_only=[])
    assert rs.source_lang == "en" and rs.auto_applied == []
