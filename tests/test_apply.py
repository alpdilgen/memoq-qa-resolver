import shutil
from pathlib import Path
from qa_engine.parser import parse_mqxliff
from qa_engine.casebuilder import build_cases
from qa_engine.models import Decision
from qa_engine.apply import apply_decisions

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def _setup(tmp_path):
    src = tmp_path / "in.mqxliff"
    shutil.copy(FIXTURE, src)
    return src


def test_false_positive_marks_ignored(tmp_path):
    src = _setup(tmp_path)
    out = tmp_path / "out.mqxliff"
    decisions = {"T_kouti": Decision("T_kouti", "false_positive", "trailing space", "high")}
    cases = build_cases(parse_mqxliff(str(src)))
    kouti = [c for c in cases
             if c.type == "target_inconsistency" and "Κουτί" in next(iter(c.distinct_targets))][0]
    decisions = {kouti.id: Decision(kouti.id, "false_positive", "trailing space", "high")}
    apply_decisions(str(src), decisions, cases, str(out))
    text = out.read_text(encoding="utf-8-sig")
    # both kouti segments' warnings now carry the ignored attribute
    assert text.count('mq:errorwarning-ignored="errorwarning-ignored"') == 2
    # targets untouched
    assert "Κουτί χρώματος:" in text


def test_pick_best_copies_chosen_target(tmp_path):
    src = _setup(tmp_path)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    sc = [c for c in cases if c.type == "source_inconsistency"][0]
    # choose tu 6's target as the better one
    chosen = [m for m in sc.members if m.tu_id == "6"][0]
    dec = Decision(sc.id, "pick_best", "standard form", "high",
                   chosen_member_id="6")
    apply_decisions(str(src), {sc.id: dec}, cases, str(out))
    text = out.read_text(encoding="utf-8-sig")
    # both Easy-to-clean targets are now the chosen variant
    assert text.count("Εύκολο στον καθαρισμό") == 2
    assert "Εύκολο στο Καθάρισμα" not in text


def test_differentiate_writes_new_target(tmp_path):
    src = _setup(tmp_path)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    tc = [c for c in cases
          if c.type == "target_inconsistency" and "Ωκεαν" in next(iter(c.distinct_targets))][0]
    dec = Decision(tc.id, "differentiate", "distinct colors", "high",
                   differentiated=[{"source_key": "Ocean Deep Sand", "new_target": "Ωκεανός Βαθιά Άμμος"}])
    apply_decisions(str(src), {tc.id: dec}, cases, str(out))
    text = out.read_text(encoding="utf-8-sig")
    assert "Ωκεανός Βαθιά Άμμος" in text


def test_makes_backup(tmp_path):
    src = _setup(tmp_path)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    apply_decisions(str(src), {}, cases, str(out))
    assert (Path(str(src) + ".bak")).exists()


def test_output_is_well_formed(tmp_path):
    src = _setup(tmp_path)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    apply_decisions(str(src), {}, cases, str(out))
    # re-parsing must not raise
    assert len(parse_mqxliff(str(out))) == 6


def test_whitespace_fix_sets_target_inner(tmp_path):
    import shutil, re
    src = tmp_path / "in.mqxliff"; shutil.copy(FIXTURE, src)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    ws_fixes = [{"tu_id": "1", "segmentguid": "g1",
                 "new_target_inner": "Κουτί χρώματος: ", "old_preview": "", "new_preview": ""}]
    apply_decisions(str(src), {}, cases, str(out), ws_fixes=ws_fixes)
    text = out.read_text(encoding="utf-8-sig")
    m = re.search(r'segmentguid="g1".*?<target[^>]*>(.*?)</target>', text, re.S)
    assert m.group(1) == "Κουτί χρώματος: "


def test_whitespace_fix_and_ignore_coexist(tmp_path):
    import shutil
    from qa_engine.models import Decision
    src = tmp_path / "in.mqxliff"; shutil.copy(FIXTURE, src)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    kouti = [c for c in cases if c.type == "target_inconsistency"
             and "Κουτί" in next(iter(c.distinct_targets))][0]
    decisions = {kouti.id: Decision(kouti.id, "false_positive", "ws", "high")}
    ws_fixes = [{"tu_id": "1", "segmentguid": "g1",
                 "new_target_inner": "Κουτί χρώματος:", "old_preview": "", "new_preview": ""}]
    apply_decisions(str(src), decisions, cases, str(out), ws_fixes=ws_fixes)
    text = out.read_text(encoding="utf-8-sig")
    assert 'mq:errorwarning-ignored="errorwarning-ignored"' in text


def test_differentiate_tag_mismatch_skips_member_without_crashing(tmp_path):
    import shutil
    from qa_engine.parser import parse_mqxliff
    from qa_engine.casebuilder import build_cases
    from qa_engine.models import Decision
    from qa_engine.apply import apply_decisions
    FIX = __import__("pathlib").Path(__file__).parent / "fixtures" / "sample.mqxliff"
    src = tmp_path / "in.mqxliff"; shutil.copy(FIX, src)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    tc = [c for c in cases if c.type == "target_inconsistency"
          and "Ωκεαν" in next(iter(c.distinct_targets))][0]
    # new_target with a bogus marker that is NOT in the member's target_tags
    dec = Decision(tc.id, "differentiate", "x", "high",
                   differentiated=[{"source_key": "Ocean Deep Sand",
                                    "new_target": "Άμμος ⟦9⟧"}])
    skipped = apply_decisions(str(src), {tc.id: dec}, cases, str(out))  # must NOT raise
    assert any(t == "3" or t == "4" for (_c, t, _r) in skipped) or len(skipped) >= 1
    # output still well-formed and the bogus target was NOT written
    assert "⟦9⟧" not in out.read_text(encoding="utf-8-sig")


def test_apply_handles_ampersand_in_target(tmp_path):
    import shutil
    from qa_engine.parser import parse_mqxliff
    from qa_engine.casebuilder import build_cases
    src = tmp_path / "in.mqxliff"
    src.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">\n'
        '<file original="c" source-language="en" target-language="el" datatype="x-memoq"><body>\n'
        '<trans-unit id="1" mq:status="C" mq:segmentguid="g1">\n'
        '<source xml:space="preserve">A &amp; B</source>\n'
        '<target xml:space="preserve">   Α &amp; Β   </target>\n'
        '</trans-unit>\n'
        '</body></file></xliff>\n', encoding="utf-8")
    out = tmp_path / "out.mqxliff"
    members = parse_mqxliff(str(src))
    from qa_engine.whitespace import compute_ws_fixes, normalize_members
    ws = compute_ws_fixes(members)
    normalize_members(members)
    cases = build_cases(members)
    apply_decisions(str(src), {}, cases, str(out), ws_fixes=ws)   # must not raise
    from lxml import etree
    etree.parse(str(out))                                         # output valid
    assert "&amp; Β" in out.read_text(encoding="utf-8-sig")       # ampersand preserved/escaped
