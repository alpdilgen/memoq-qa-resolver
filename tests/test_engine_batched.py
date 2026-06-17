from qa_engine.engine import analyze, reconcile
from qa_engine.checkpoint import Checkpoint


def _seg(i):
    return (f'<trans-unit id="{i}" mq:status="C" mq:segmentguid="g{i}">'
            f'<source xml:space="preserve">term{i}</source>'
            f'<target xml:space="preserve">x{i}</target>'
            '<mq:warnings40><mq:errorwarning mq:errorwarning-code="03091" '
            'mq:errorwarning-problemname="missing term" mq:errorwarning-localizationargs="t" />'
            '</mq:warnings40></trans-unit>')


DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
    '<file original="c" source-language="en" target-language="tr" datatype="x-memoq"><body>\n'
    + "\n".join(_seg(i) for i in (1, 2, 3))
    + '\n</body></file></xliff>\n'
).encode("utf-8")


class _BatchFake:
    def __init__(self):
        self.calls = 0
    def resolve(self, system, user, schema):
        self.calls += 1
        if "segments" in schema.get("properties", {}):          # batch call
            segs = [{"segment_id": g, "code_verdicts": [{"code": "3091", "verdict": "fix"}],
                     "fixed_target": f"FIX{g}", "confidence": 100, "rationale": "r"}
                    for g in ("g1", "g2", "g3") if f"SEGMENT {g}" in user]
            return {"segments": segs}
        return {"code_verdicts": [{"code": "3091", "verdict": "fix"}],
                "fixed_target": "FIX", "confidence": 100, "rationale": "r"}


class _Boom:
    def resolve(self, system, user, schema):
        raise AssertionError("AI should not be called when results are cached")


def test_batching_makes_fewer_calls():
    fake = _BatchFake()
    rs = analyze(DOC, ai_client=fake, batch_size=2)
    reconcile(rs)
    assert rs.total_issues == 3
    assert fake.calls == 2                       # 3 segments, batch_size 2 -> 2 calls (not 3)
    assert len(rs.auto_applied) == 3 and len(rs.pending) == 0


def test_checkpoint_resume_uses_cache_no_ai(tmp_path):
    path = str(tmp_path / "ck.json")
    rs1 = analyze(DOC, ai_client=_BatchFake(), batch_size=2, checkpoint=Checkpoint(path))
    reconcile(rs1)
    # Second run with a client that explodes if called — must complete purely from cache.
    rs2 = analyze(DOC, ai_client=_Boom(), batch_size=2, checkpoint=Checkpoint(path))
    reconcile(rs2)
    assert rs2.total_issues == 3 and len(rs2.auto_applied) == 3
