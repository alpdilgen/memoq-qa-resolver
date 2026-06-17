from qa_engine.checkpoint import Checkpoint, content_key
from qa_engine.models import ResolvedItem, Resolution


def _item():
    return ResolvedItem("g1:3073", "g1", "1", "3073", "space after sign",
                        "a; b", "a;b", "a; b",
                        Resolution(action="fix", new_target="a; b", needs_approval=False,
                                   strategy="ai", ignore_codes=["3100"],
                                   new_target_tokens="a; b"),
                        issue_count=2, tags={"1": "<x/>"}, proposed_tokens="a; b")


def test_content_key_stable_and_distinct():
    assert content_key(b"abc") == content_key(b"abc")
    assert content_key(b"abc") != content_key(b"abd")


def test_save_flush_reload_roundtrip(tmp_path):
    p = str(tmp_path / "ck.json")
    cp = Checkpoint(p)
    assert not cp.has("g1")
    cp.save_item(_item())
    cp.flush()

    cp2 = Checkpoint(p)                       # simulate a fresh run (rerun)
    assert cp2.has("g1")
    it = cp2.get_item("g1")
    assert it.segmentguid == "g1" and it.issue_count == 2
    assert it.resolution.new_target == "a; b"
    assert it.resolution.ignore_codes == ["3100"]
    assert it.tags == {"1": "<x/>"}
    assert len(cp2.all_items()) == 1


def test_corrupt_cache_starts_fresh(tmp_path):
    p = tmp_path / "ck.json"
    p.write_text("{ this is not json", encoding="utf-8")
    cp = Checkpoint(str(p))                   # must not raise
    assert cp.all_items() == []
