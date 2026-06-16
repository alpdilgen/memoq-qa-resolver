# Inconsistency Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable Python CLI tool that reads a memoQ `.mqxliff`, resolves its inconsistency QA warnings with Claude Opus 4.8, produces a review report, and (after approval) writes a corrected mqxliff whose inconsistency warnings are gone on re-import.

**Architecture:** Two-phase pipeline. `analyze` parses the mqxliff, groups warnings into *cases*, gathers context, asks Claude (one structured call per case) to classify each case as `false_positive` / `pick_best` / `differentiate`, and writes `report.html` + `decisions.json` without touching the source. `apply` reads `decisions.json` and edits the mqxliff with targeted, segmentguid-keyed string edits (copy a better target's XML, write a differentiated target, or flag a warning `ignored`), writing a new `*.FIXED.mqxliff` plus a `.bak` backup.

**Tech Stack:** Python 3.11+, `anthropic` SDK (Claude Opus 4.8, adaptive thinking, structured outputs), `lxml` for read-side parsing, stdlib `re`/string editing for write-side, `pytest` for tests.

---

### Task 0: Project scaffold, git, dependencies

**Files:**
- Create: `inconsistency_resolver/__init__.py`
- Create: `tests/__init__.py`
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`

- [ ] **Step 1: Initialize git (directory is not yet a repo)**

Run:
```bash
cd "C:/Users/ada/Documents/Claude/Projects/QA resolvers/Inconsistency"
git init
```
Expected: `Initialized empty Git repository`.

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
*.FIXED.mqxliff
*.bak
.env
out/
```

- [ ] **Step 3: Create `requirements.txt`**

```
anthropic>=0.69
lxml>=5.0
pytest>=8.0
```

- [ ] **Step 4: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 5: Create empty package files**

`inconsistency_resolver/__init__.py`:
```python
"""memoQ mqxliff inconsistency resolver."""
__version__ = "0.1.0"
```

`tests/__init__.py`:
```python
```

- [ ] **Step 6: Verify pytest runs (no tests yet)**

Run: `python -m pytest`
Expected: `no tests ran` (exit code 5) — confirms pytest is wired.

- [ ] **Step 7: Commit**

```bash
git add inconsistency_resolver tests requirements.txt pytest.ini .gitignore
git commit -m "chore: scaffold inconsistency_resolver project"
```

---

### Task 1: Data models

**Files:**
- Create: `inconsistency_resolver/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from inconsistency_resolver.models import Member, Case, Decision


def test_member_roundtrip_fields():
    m = Member(
        tu_id="1",
        segmentguid="abc",
        source_text="Secure Fit",
        target_text="Asfalis",
        source_tags={},
        target_tags={},
        status="PartiallyEdited",
        tm_match=None,
        warning_keys=[("inconsistent translation", "Secure Fit\tAsfalis")],
    )
    assert m.tu_id == "1"
    assert m.warning_keys[0][0] == "inconsistent translation"


def test_case_distinct_counts():
    members = [
        Member("1", "g1", "Color box: ", "Kouti", {}, {}, "Edited", None, []),
        Member("2", "g2", "Color box:", "Kouti", {}, {}, "Edited", None, []),
    ]
    c = Case(id="c1", type="target_inconsistency", members=members,
             mechanical_diff="trailing whitespace")
    assert c.distinct_sources == {"Color box: ", "Color box:"}
    assert c.distinct_targets == {"Kouti"}


def test_decision_defaults():
    d = Decision(case_id="c1", category="false_positive",
                 rationale="sources differ only by trailing space",
                 confidence="high")
    assert d.chosen_member_id is None
    assert d.differentiated == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'inconsistency_resolver.models'`.

- [ ] **Step 3: Write minimal implementation**

`inconsistency_resolver/models.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Member:
    tu_id: str
    segmentguid: str
    source_text: str            # tokenized (inline tags -> markers)
    target_text: str            # tokenized
    source_tags: dict           # marker -> original tag XML
    target_tags: dict
    status: str
    tm_match: Optional[str]     # target of best <mq:insertedmatch>, if any
    warning_keys: list          # list of (problemname, localizationargs)


@dataclass
class Case:
    id: str
    type: str                   # "target_inconsistency" | "source_inconsistency"
    members: list
    mechanical_diff: str = ""

    @property
    def distinct_sources(self) -> set:
        return {m.source_text for m in self.members}

    @property
    def distinct_targets(self) -> set:
        return {m.target_text for m in self.members}


@dataclass
class Decision:
    case_id: str
    category: str               # false_positive | pick_best | differentiate | needs_manual
    rationale: str
    confidence: str             # high | medium | low
    chosen_member_id: Optional[str] = None
    differentiated: list = field(default_factory=list)  # [{"source_key","new_target"}]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/models.py tests/test_models.py
git commit -m "feat: add core data models"
```

---

### Task 2: Inline-tag tokenizer

Inline tags inside `<source>`/`<target>` (e.g. `<ph id="1">…</ph>`, `<x id=".."/>`, `<mq:ch val=".."/>`, paired `<g …>…</g>`) must be hidden from the AI as ordered markers and restored exactly. `<ph>` and self-closing tags become one opaque marker each; `<g>` open and `</g>` close become separate markers so translatable text between them survives.

**Files:**
- Create: `inconsistency_resolver/tags.py`
- Test: `tests/test_tags.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tags.py`:
```python
from inconsistency_resolver.tags import tokenize, detokenize

PH = '<ph id="1">&lt;x id=&quot;34&quot; /&gt;</ph>'


def test_tokenize_ph_is_opaque_marker():
    text = f"Asfalis Efarmogi{PH}"
    toks, mapping = tokenize(text)
    assert "Asfalis Efarmogi" in toks
    assert "<ph" not in toks                  # tag hidden
    assert len(mapping) == 1
    assert detokenize(toks, mapping) == text  # exact round-trip


def test_tokenize_self_closing_and_paired_g():
    text = 'A<x id="5"/>B<g id="2">mid</g>C'
    toks, mapping = tokenize(text)
    assert "<x" not in toks and "<g" not in toks
    assert "mid" in toks                      # paired g content stays visible
    assert detokenize(toks, mapping) == text


def test_detokenize_rejects_missing_marker():
    text = f"X{PH}"
    toks, mapping = tokenize(text)
    broken = toks.replace("⟦", "")            # corrupt marker
    import pytest
    with pytest.raises(ValueError):
        detokenize(broken, mapping)


def test_marker_multiset_helper():
    from inconsistency_resolver.tags import markers_in
    text = f"A{PH}B<x id=\"5\"/>"
    toks, mapping = tokenize(text)
    assert markers_in(toks) == set(mapping.keys())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tags.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'inconsistency_resolver.tags'`.

- [ ] **Step 3: Write minimal implementation**

`inconsistency_resolver/tags.py`:
```python
import re

# Order matters: match ph (with its content) and self-closing tags before
# the generic paired-g open/close.
_TAG_RE = re.compile(
    r'<bpt\b[^>]*>.*?</bpt>'    # paired begin-tag, opaque (escaped catalog value)
    r'|<ept\b[^>]*>.*?</ept>'   # paired end-tag, opaque
    r'|<it\b[^>]*>.*?</it>'     # isolated tag, opaque
    r'|<ph\b[^>]*>.*?</ph>'     # ph wraps original-format codes -> opaque
    r'|<x\b[^>]*/>'             # self-closing placeholder
    r'|<mq:ch\b[^>]*/>'        # self-closing memoQ char
    r'|<g\b[^>]*>'             # paired open
    r'|</g>',                   # paired close
    re.DOTALL,
)

_OPEN, _CLOSE = "⟦", "⟧"   # ⟦ ⟧  private-ish brackets unlikely in text
_MARK_RE = re.compile(_OPEN + r"(\d+)" + _CLOSE)


def tokenize(xml_text: str):
    """Replace inline tags with ordered markers ⟦N⟧. Returns (text, {marker: xml})."""
    mapping = {}
    counter = [0]

    def repl(m):
        counter[0] += 1
        marker = f"{_OPEN}{counter[0]}{_CLOSE}"
        mapping[marker] = m.group(0)
        return marker

    return _TAG_RE.sub(repl, xml_text), mapping


def markers_in(text: str) -> set:
    return {f"{_OPEN}{n}{_CLOSE}" for n in _MARK_RE.findall(text)}


def detokenize(text: str, mapping: dict) -> str:
    """Restore original tags. Raises ValueError if markers don't match mapping."""
    if markers_in(text) != set(mapping.keys()):
        raise ValueError(
            f"marker mismatch: text has {markers_in(text)}, mapping has {set(mapping)}"
        )
    out = text
    for marker, xml in mapping.items():
        out = out.replace(marker, xml)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tags.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/tags.py tests/test_tags.py
git commit -m "feat: add inline-tag tokenizer with round-trip guarantee"
```

---

### Task 3: mqxliff parser (read-side)

Parse the file into a list of trans-unit records: id, segmentguid, raw inner-XML of `<source>`/`<target>`, status, best TM match target, and the inconsistency warnings present. Read-only; uses lxml.

**Files:**
- Create: `inconsistency_resolver/parser.py`
- Test: `tests/test_parser.py`
- Create: `tests/fixtures/sample.mqxliff`

- [ ] **Step 1: Create the test fixture**

`tests/fixtures/sample.mqxliff` (small, hand-built; covers target-inconsistency false-positive, target-inconsistency real, and source-inconsistency):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:mq="MQXliff">
<file original="check" source-language="en" target-language="el" datatype="x-memoq">
<body>
<trans-unit id="1" mq:status="Confirmed" mq:segmentguid="g1">
<source xml:space="preserve">Color box: </source>
<target xml:space="preserve">Κουτί χρώματος:</target>
<mq:warnings40>
<mq:errorwarning mq:errorwarning-code="03101" mq:errorwarning-categoryid="2" mq:errorwarning-ignorable="errorwarning-ignorable" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-longdesc="The target segment is also the translation of: Color box:" mq:errorwarning-localizationargs="Color box:&#9;Κουτί χρώματος:" />
</mq:warnings40>
</trans-unit>
<trans-unit id="2" mq:status="Confirmed" mq:segmentguid="g2">
<source xml:space="preserve">Color box:</source>
<target xml:space="preserve">Κουτί χρώματος:</target>
<mq:warnings40>
<mq:errorwarning mq:errorwarning-code="03101" mq:errorwarning-categoryid="2" mq:errorwarning-ignorable="errorwarning-ignorable" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-longdesc="The target segment is also the translation of: Color box: " mq:errorwarning-localizationargs="Color box: &#9;Κουτί χρώματος:" />
</mq:warnings40>
</trans-unit>
<trans-unit id="3" mq:status="Confirmed" mq:segmentguid="g3">
<source xml:space="preserve">Ocean Deep Sand</source>
<target xml:space="preserve">Ωκεανός Βαθύ Σοφιστικέ</target>
<mq:warnings40>
<mq:errorwarning mq:errorwarning-code="03101" mq:errorwarning-categoryid="2" mq:errorwarning-ignorable="errorwarning-ignorable" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-longdesc="The target segment is also the translation of: Ocean Deep Sage" mq:errorwarning-localizationargs="Ocean Deep Sage&#9;Ωκεανός Βαθύ Σοφιστικέ" />
</mq:warnings40>
</trans-unit>
<trans-unit id="4" mq:status="Confirmed" mq:segmentguid="g4">
<source xml:space="preserve">Ocean Deep Sage</source>
<target xml:space="preserve">Ωκεανός Βαθύ Σοφιστικέ</target>
<mq:warnings40>
<mq:errorwarning mq:errorwarning-code="03101" mq:errorwarning-categoryid="2" mq:errorwarning-ignorable="errorwarning-ignorable" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-longdesc="The target segment is also the translation of: Ocean Deep Sand" mq:errorwarning-localizationargs="Ocean Deep Sand&#9;Ωκεανός Βαθύ Σοφιστικέ" />
</mq:warnings40>
</trans-unit>
<trans-unit id="5" mq:status="Confirmed" mq:segmentguid="g5">
<source xml:space="preserve">Easy to clean</source>
<target xml:space="preserve">Εύκολο στο Καθάρισμα</target>
<mq:warnings40>
<mq:errorwarning mq:errorwarning-code="03101" mq:errorwarning-categoryid="2" mq:errorwarning-ignorable="errorwarning-ignorable" mq:errorwarning-problemname="inconsistent translation" mq:errorwarning-longdesc="The same segment was also translated as: Εύκολο στον καθαρισμό" mq:errorwarning-localizationargs="Easy to clean&#9;Εύκολο στον καθαρισμό" />
</mq:warnings40>
</trans-unit>
<trans-unit id="6" mq:status="Confirmed" mq:segmentguid="g6">
<source xml:space="preserve">Easy to clean</source>
<target xml:space="preserve">Εύκολο στον καθαρισμό</target>
</trans-unit>
</body>
</file>
</xliff>
```

- [ ] **Step 2: Write the failing test**

`tests/test_parser.py`:
```python
from pathlib import Path
from inconsistency_resolver.parser import parse_mqxliff

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_parse_returns_all_trans_units():
    units = parse_mqxliff(str(FIXTURE))
    assert len(units) == 6
    assert units[0].tu_id == "1"
    assert units[0].segmentguid == "g1"


def test_parse_extracts_source_and_target_text():
    units = parse_mqxliff(str(FIXTURE))
    assert units[0].source_text == "Color box: "
    assert units[0].target_text == "Κουτί χρώματος:"


def test_parse_extracts_warnings():
    units = parse_mqxliff(str(FIXTURE))
    pn, args = units[0].warning_keys[0]
    assert pn == "inconsistent translation"
    assert "Κουτί χρώματος:" in args
    assert units[5].warning_keys == []        # tu 6 has no warnings
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'inconsistency_resolver.parser'`.

- [ ] **Step 4: Write minimal implementation**

`inconsistency_resolver/parser.py`:
```python
from lxml import etree
from xml.sax.saxutils import escape as _xml_escape
from .models import Member
from .tags import tokenize

_XLIFF = "urn:oasis:names:tc:xliff:document:1.2"
_MQ = "MQXliff"
_NS = {"x": _XLIFF, "mq": _MQ}


def _inner_xml(elem) -> str:
    """Serialize an element's inner content (text + child tags), no outer tag.

    `with_tail=False` is required: etree.tostring includes the child's tail by
    default, and we append child.tail ourselves — without it, tail text doubles.
    We also strip the namespace declarations lxml injects onto a standalone
    serialized child so the fragment matches the original file form byte-for-byte.
    """
    if elem is None:
        return ""
    # lxml .text/.tail return DECODED text (&amp;->&, &lt;-><); re-escape the
    # text nodes so the reconstructed inner-XML is valid when written back.
    # Child fragments from etree.tostring are already escaped — don't re-escape.
    parts = [_xml_escape(elem.text or "")]
    for child in elem:
        frag = etree.tostring(child, encoding="unicode", with_tail=False)
        frag = frag.replace(' xmlns="urn:oasis:names:tc:xliff:document:1.2"', '')
        frag = frag.replace(' xmlns:mq="MQXliff"', '')
        frag = frag.replace(' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"', '')
        parts.append(frag)
        parts.append(_xml_escape(child.tail or ""))
    return "".join(parts)


def parse_mqxliff(path: str) -> list:
    tree = etree.parse(path)
    root = tree.getroot()
    members = []
    for tu in root.iter(f"{{{_XLIFF}}}trans-unit"):
        tu_id = tu.get("id")
        segguid = tu.get(f"{{{_MQ}}}segmentguid")
        status = tu.get(f"{{{_MQ}}}status", "")

        source_el = tu.find(f"{{{_XLIFF}}}source")
        target_el = tu.find(f"{{{_XLIFF}}}target")
        src_raw = _inner_xml(source_el)
        tgt_raw = _inner_xml(target_el)
        src_tok, src_map = tokenize(src_raw)
        tgt_tok, tgt_map = tokenize(tgt_raw)

        # best TM match target, if any
        tm = None
        im = tu.find(f"{{{_MQ}}}insertedmatch")
        if im is not None:
            im_tgt = im.find(f"{{{_XLIFF}}}target")
            if im_tgt is not None:
                tm = _inner_xml(im_tgt)

        warnings = []
        for ew in tu.iter(f"{{{_MQ}}}errorwarning"):
            pn = ew.get(f"{{{_MQ}}}errorwarning-problemname", "")
            args = ew.get(f"{{{_MQ}}}errorwarning-localizationargs", "")
            warnings.append((pn, args))

        members.append(Member(
            tu_id=tu_id, segmentguid=segguid,
            source_text=src_tok, target_text=tgt_tok,
            source_tags=src_map, target_tags=tgt_map,
            status=status, tm_match=tm, warning_keys=warnings,
        ))
    return members
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_parser.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add inconsistency_resolver/parser.py tests/test_parser.py tests/fixtures/sample.mqxliff
git commit -m "feat: parse mqxliff into trans-unit members"
```

---

### Task 4: Case builder + mechanical diff

Group members that carry inconsistency warnings into cases. Two case types: target-inconsistency (`longdesc` starts with "The target segment is also the translation of") groups by identical target; source-inconsistency ("The same segment was also translated as") groups by identical source. Also compute a human-readable mechanical diff between the differing strings for false-positive transparency.

**Files:**
- Create: `inconsistency_resolver/casebuilder.py`
- Test: `tests/test_casebuilder.py`

- [ ] **Step 1: Write the failing test**

`tests/test_casebuilder.py`:
```python
from pathlib import Path
from inconsistency_resolver.parser import parse_mqxliff
from inconsistency_resolver.casebuilder import build_cases, describe_diff

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_builds_three_cases():
    cases = build_cases(parse_mqxliff(str(FIXTURE)))
    types = sorted(c.type for c in cases)
    # two target_inconsistency groups (Κουτί, Ωκεανός) + one source_inconsistency (Easy to clean)
    assert types == ["source_inconsistency", "target_inconsistency", "target_inconsistency"]


def test_target_case_groups_by_target():
    cases = build_cases(parse_mqxliff(str(FIXTURE)))
    kouti = [c for c in cases
             if c.type == "target_inconsistency" and "Κουτί" in next(iter(c.distinct_targets))][0]
    assert {m.tu_id for m in kouti.members} == {"1", "2"}


def test_source_case_groups_by_source():
    cases = build_cases(parse_mqxliff(str(FIXTURE)))
    src = [c for c in cases if c.type == "source_inconsistency"][0]
    assert {m.tu_id for m in src.members} == {"5", "6"}
    assert src.distinct_targets == {"Εύκολο στο Καθάρισμα", "Εύκολο στον καθαρισμό"}


def test_describe_diff_trailing_space():
    assert "whitespace" in describe_diff(["Color box: ", "Color box:"]).lower()


def test_describe_diff_typo():
    out = describe_diff(["Blister card:", "Bliser card:"]).lower()
    assert "differ" in out or "typo" in out or "char" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_casebuilder.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`inconsistency_resolver/casebuilder.py`:
```python
import difflib
from .models import Case


def _has_inconsistency(member) -> bool:
    return any(pn == "inconsistent translation" for pn, _ in member.warning_keys)


def build_cases(members: list) -> list:
    warned = [m for m in members if _has_inconsistency(m)]

    # target-inconsistency: group warned members by identical (tokenized) target
    by_target = {}
    for m in warned:
        by_target.setdefault(m.target_text, []).append(m)
    # source-inconsistency: group warned members by identical (tokenized) source
    by_source = {}
    for m in warned:
        by_source.setdefault(m.source_text, []).append(m)

    cases = []
    seen_ids = set()
    cid = 0

    # source-inconsistency first: a source mapping to >1 distinct target
    for src, group in by_source.items():
        targets = {m.target_text for m in group}
        # pull in non-warned members that share this source (the "other" variant)
        same_source = [m for m in members if m.source_text == src]
        all_targets = {m.target_text for m in same_source}
        if len(all_targets) > 1:
            cid += 1
            cases.append(Case(
                id=f"S{cid}", type="source_inconsistency",
                members=same_source,
                mechanical_diff=describe_diff(sorted(all_targets)),
            ))
            seen_ids.update(m.tu_id for m in same_source)

    # target-inconsistency: a target mapping to >1 distinct source
    for tgt, group in by_target.items():
        if any(m.tu_id in seen_ids for m in group):
            continue
        same_target = [m for m in members if m.target_text == tgt]
        all_sources = {m.source_text for m in same_target}
        if len(all_sources) > 1:
            cid += 1
            cases.append(Case(
                id=f"T{cid}", type="target_inconsistency",
                members=same_target,
                mechanical_diff=describe_diff(sorted(all_sources)),
            ))
            seen_ids.update(m.tu_id for m in same_target)

    return cases


def describe_diff(strings: list) -> str:
    """Plain-English mechanical difference between variant strings."""
    if len(strings) < 2:
        return "single variant"
    a, b = strings[0], strings[1]
    if a.strip() == b.strip() and a != b:
        return "differ only by leading/trailing whitespace"
    if a.replace(" ", "") == b.replace(" ", "") and a != b:
        return "differ only by internal whitespace"
    if a.lower() == b.lower():
        return "differ only by letter case"
    sm = difflib.SequenceMatcher(None, a, b)
    if sm.ratio() > 0.93:   # 0.96 'Bliser'/'Blister' = typo; 0.87 'Sand'/'Sage' = different
        return f"differ by a few characters (likely a typo): {a!r} vs {b!r}"
    return f"meaningfully different: {a!r} vs {b!r}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_casebuilder.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/casebuilder.py tests/test_casebuilder.py
git commit -m "feat: group warnings into cases with mechanical diff"
```

---

### Task 5: Context gathering (neighbors, frequency, glossary)

Enrich each case with the context the AI needs: source variant frequencies, neighbor segments around each member, glossary hits. Glossary is a simple TSV (`source<TAB>target`), optional.

**Files:**
- Create: `inconsistency_resolver/glossary.py`
- Create: `inconsistency_resolver/context.py`
- Test: `tests/test_glossary.py`
- Test: `tests/test_context.py`

- [ ] **Step 1: Write the failing glossary test**

`tests/test_glossary.py`:
```python
from inconsistency_resolver.glossary import load_glossary, lookup


def test_load_and_lookup(tmp_path):
    p = tmp_path / "gloss.tsv"
    p.write_text("Easy to clean\tΕύκολο στον καθαρισμό\nPremium\tPremium\n",
                 encoding="utf-8")
    g = load_glossary(str(p))
    assert lookup(g, "easy to clean") == "Εύκολο στον καθαρισμό"
    assert lookup(g, "missing") is None


def test_load_none_returns_empty():
    g = load_glossary(None)
    assert g == {}
```

- [ ] **Step 2: Run it; verify failure**

Run: `python -m pytest tests/test_glossary.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement glossary**

`inconsistency_resolver/glossary.py`:
```python
def load_glossary(path):
    """Load a source<TAB>target TSV. Returns {} when path is None/missing."""
    if not path:
        return {}
    table = {}
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            src, tgt = line.split("\t", 1)
            table[src.strip().lower()] = tgt.strip()
    return table


def lookup(table, source_text):
    return table.get(source_text.strip().lower())
```

- [ ] **Step 4: Run glossary test; verify pass**

Run: `python -m pytest tests/test_glossary.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Write the failing context test**

`tests/test_context.py`:
```python
from pathlib import Path
from inconsistency_resolver.parser import parse_mqxliff
from inconsistency_resolver.casebuilder import build_cases
from inconsistency_resolver.context import build_case_payload

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


def test_payload_has_variants_and_frequency():
    members = parse_mqxliff(str(FIXTURE))
    cases = build_cases(members)
    case = [c for c in cases if c.type == "source_inconsistency"][0]
    payload = build_case_payload(case, members, glossary={})
    assert payload["type"] == "source_inconsistency"
    assert payload["mechanical_diff"]
    keys = {v["text"] for v in payload["target_variants"]}
    assert "Εύκολο στο Καθάρισμα" in keys
    assert all("count" in v for v in payload["target_variants"])


def test_payload_includes_glossary_hit():
    members = parse_mqxliff(str(FIXTURE))
    cases = build_cases(members)
    case = [c for c in cases if c.type == "source_inconsistency"][0]
    payload = build_case_payload(case, members,
                                 glossary={"easy to clean": "Εύκολο στον καθαρισμό"})
    assert payload["glossary_suggestion"] == "Εύκολο στον καθαρισμό"
```

- [ ] **Step 6: Run it; verify failure**

Run: `python -m pytest tests/test_context.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 7: Implement context**

`inconsistency_resolver/context.py`:
```python
from collections import Counter
from .glossary import lookup


def build_case_payload(case, all_members, glossary):
    """Build the JSON-serializable payload sent to the AI for one case."""
    src_counts = Counter(m.source_text for m in case.members)
    tgt_counts = Counter(m.target_text for m in case.members)

    source_variants = [{"key": s, "text": s, "count": c} for s, c in src_counts.items()]
    target_variants = [{"text": t, "count": c} for t, c in tgt_counts.items()]

    # glossary suggestion keyed on the (first) source text
    gloss = None
    for m in case.members:
        hit = lookup(glossary, m.source_text)
        if hit:
            gloss = hit
            break

    # one TM suggestion if any member carries one
    tm = next((m.tm_match for m in case.members if m.tm_match), None)

    return {
        "case_id": case.id,
        "type": case.type,
        "mechanical_diff": case.mechanical_diff,
        "source_variants": source_variants,
        "target_variants": target_variants,
        "members": [{"tu_id": m.tu_id, "source": m.source_text, "target": m.target_text}
                    for m in case.members],
        "glossary_suggestion": gloss,
        "tm_suggestion": tm,
    }
```

- [ ] **Step 8: Run context test; verify pass**

Run: `python -m pytest tests/test_context.py -v`
Expected: PASS (2 passed).

- [ ] **Step 9: Commit**

```bash
git add inconsistency_resolver/glossary.py inconsistency_resolver/context.py tests/test_glossary.py tests/test_context.py
git commit -m "feat: glossary loader and per-case AI payload builder"
```

---

### Task 6: AI client (Claude Opus 4.8, structured output)

One structured call per case. The system prompt (rules + category definitions + glossary) is cached; the case payload is the per-request part. Output is validated against a JSON schema. The client is injectable so tests can pass a fake.

**Files:**
- Create: `inconsistency_resolver/ai.py`
- Test: `tests/test_ai.py`

- [ ] **Step 1: Write the failing test (with a fake client)**

`tests/test_ai.py`:
```python
import json
from inconsistency_resolver.ai import classify_case, DECISION_SCHEMA, build_system_prompt


class FakeMessage:
    def __init__(self, payload):
        self.content = [type("B", (), {"type": "text", "text": json.dumps(payload)})()]


class FakeMessages:
    def __init__(self, payload):
        self._payload = payload
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeMessage(self._payload)


class FakeClient:
    def __init__(self, payload):
        self.messages = FakeMessages(payload)


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
    kw = fake.messages.last_kwargs
    assert kw["model"] == "claude-opus-4-8"
    assert kw["output_config"]["format"]["schema"] == DECISION_SCHEMA
    assert kw["thinking"] == {"type": "adaptive"}


def test_system_prompt_includes_categories_and_glossary():
    sp = build_system_prompt(glossary_text="Easy to clean = X")
    assert "false_positive" in sp and "pick_best" in sp and "differentiate" in sp
    assert "Easy to clean = X" in sp
```

- [ ] **Step 2: Run it; verify failure**

Run: `python -m pytest tests/test_ai.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement the AI client**

`inconsistency_resolver/ai.py`:
```python
import json
from .models import Decision

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string",
                     "enum": ["false_positive", "pick_best", "differentiate"]},
        "rationale": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "chosen_variant_key": {"type": ["string", "null"]},
        "differentiated": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_key": {"type": "string"},
                    "new_target": {"type": "string"},
                },
                "required": ["source_key", "new_target"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["category", "rationale", "confidence"],
    "additionalProperties": False,
}

_RULES = """You resolve memoQ translation inconsistency QA warnings (EN source -> EL target).
Inline tags are hidden as markers like ⟦1⟧ — never alter, add, or drop a marker.

Each case is one of:
- target_inconsistency: one target used for several DIFFERENT sources.
- source_inconsistency: one source translated as several DIFFERENT targets.

Classify into exactly one category:
- false_positive: the differing strings are equivalent (whitespace, punctuation,
  a source typo, casing) and the existing target is correct for all members.
  Choose this when no translation change is warranted. The warning will be marked ignored.
- pick_best: (source_inconsistency) the source has competing targets and one
  existing target is clearly better/standard. Set chosen_variant_key to the
  TARGET text of the better variant. Do NOT invent new text.
- differentiate: (target_inconsistency) the sources are genuinely different and
  must NOT share one target (e.g. two distinct color names). For each source that
  should change, return {source_key, new_target} with corrected Greek, keeping all
  markers intact.

Prefer the in-file majority variant and any glossary/TM suggestion. Be concrete in
`rationale` — for false_positive, name the exact difference (e.g. 'trailing space',
'source typo Bliser->Blister')."""


def build_system_prompt(glossary_text: str = "") -> str:
    sp = _RULES
    if glossary_text:
        sp += "\n\nGLOSSARY (authoritative term pairs):\n" + glossary_text
    return sp


def classify_case(client, payload: dict, system_prompt: str, model: str) -> Decision:
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
        messages=[{"role": "user",
                   "content": "Resolve this inconsistency case:\n"
                              + json.dumps(payload, ensure_ascii=False, indent=2)}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    chosen_member_id = None
    if data["category"] == "pick_best" and data.get("chosen_variant_key"):
        chosen_member_id = _member_for_target(payload, data["chosen_variant_key"])

    return Decision(
        case_id=payload["case_id"],
        category=data["category"],
        rationale=data["rationale"],
        confidence=data["confidence"],
        chosen_member_id=chosen_member_id,
        differentiated=data.get("differentiated", []),
    )


def _member_for_target(payload, target_text):
    """Map the chosen target text back to a member tu_id whose target matches."""
    for m in payload.get("members", []):
        if m["target"] == target_text:
            return m["tu_id"]
    return None
```

- [ ] **Step 4: Run AI test; verify pass**

Run: `python -m pytest tests/test_ai.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/ai.py tests/test_ai.py
git commit -m "feat: Claude Opus 4.8 case classifier with structured output"
```

---

### Task 7: Report generator (HTML + decisions.json)

Write a machine-readable `decisions.json` (apply's source of truth) and a human-readable `report.html`. For `false_positive` cases the HTML must show segment numbers, the mechanical diff of the differing sources, and the AI rationale, side by side.

**Files:**
- Create: `inconsistency_resolver/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

`tests/test_report.py`:
```python
import json
from inconsistency_resolver.models import Case, Member, Decision
from inconsistency_resolver.report import write_reports


def _case_and_decision():
    members = [
        Member("1", "g1", "Color box: ", "Κουτί", {}, {}, "Edited", None,
               [("inconsistent translation", "Color box:\tΚουτί")]),
        Member("2", "g2", "Color box:", "Κουτί", {}, {}, "Edited", None,
               [("inconsistent translation", "Color box: \tΚουτί")]),
    ]
    case = Case("T1", "target_inconsistency", members,
                "differ only by leading/trailing whitespace")
    dec = Decision("T1", "false_positive",
                   "sources differ only by a trailing space; target is correct",
                   "high")
    return [case], {"T1": dec}


def test_writes_json_and_html(tmp_path):
    cases, decisions = _case_and_decision()
    write_reports(cases, decisions, str(tmp_path))
    data = json.loads((tmp_path / "decisions.json").read_text(encoding="utf-8"))
    assert data["T1"]["category"] == "false_positive"
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "T1" in html
    assert "1" in html and "2" in html              # segment numbers
    assert "trailing space" in html                 # rationale
    assert "whitespace" in html                     # mechanical diff


def test_summary_counts(tmp_path):
    cases, decisions = _case_and_decision()
    write_reports(cases, decisions, str(tmp_path))
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "false_positive: 1" in html
```

- [ ] **Step 2: Run it; verify failure**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement the report generator**

`inconsistency_resolver/report.py`:
```python
import json
import html
import os
from collections import Counter
from dataclasses import asdict


def write_reports(cases, decisions, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    _write_json(decisions, os.path.join(out_dir, "decisions.json"))
    _write_html(cases, decisions, os.path.join(out_dir, "report.html"))


def _write_json(decisions, path):
    data = {cid: asdict(d) for cid, d in decisions.items()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _esc(s):
    return html.escape(str(s))


def _write_html(cases, decisions, path):
    counts = Counter(d.category for d in decisions.values())
    case_by_id = {c.id: c for c in cases}

    rows = []
    for cid, d in decisions.items():
        c = case_by_id.get(cid)
        seg_ids = ", ".join(m.tu_id for m in c.members) if c else ""
        sources = "<br>".join(_esc(s) for s in sorted(c.distinct_sources)) if c else ""
        targets = "<br>".join(_esc(t) for t in sorted(c.distinct_targets)) if c else ""
        diff = _esc(c.mechanical_diff) if c else ""
        rows.append(f"""
        <tr class="{_esc(d.category)}">
          <td>{_esc(cid)}</td>
          <td>{_esc(d.category)}</td>
          <td>{_esc(d.confidence)}</td>
          <td>{seg_ids}</td>
          <td><b>diff:</b> {diff}<br><b>sources:</b><br>{sources}<br>
              <b>targets:</b><br>{targets}</td>
          <td>{_esc(d.rationale)}</td>
        </tr>""")

    summary = " &nbsp; ".join(f"{cat}: {n}" for cat, n in sorted(counts.items()))
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Inconsistency Resolver Report</title>
<style>
 body{{font-family:sans-serif;margin:2rem}}
 table{{border-collapse:collapse;width:100%}}
 td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;font-size:13px}}
 tr.false_positive{{background:#f3faf3}}
 tr.differentiate{{background:#fff6e6}}
 tr.pick_best{{background:#eef3fb}}
 tr.needs_manual{{background:#fdecec}}
</style></head><body>
<h1>Inconsistency Resolver Report</h1>
<p><b>Summary:</b> {summary}</p>
<table>
<tr><th>Case</th><th>Category</th><th>Confidence</th><th>Segments</th>
    <th>Diff / Sources / Targets</th><th>Rationale</th></tr>
{''.join(rows)}
</table></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
```

- [ ] **Step 4: Run report test; verify pass**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/report.py tests/test_report.py
git commit -m "feat: HTML + JSON report with false-positive transparency"
```

---

### Task 8: Apply decisions to mqxliff

Read the file as text (UTF-8 with BOM, no newline translation). Rewrite only the trans-units named by decisions, keeping every other byte verbatim. Back up the original. Validate the output before returning.

**Files:**
- Create: `inconsistency_resolver/apply.py`
- Test: `tests/test_apply.py`

- [ ] **Step 1: Write the failing test**

`tests/test_apply.py`:
```python
import shutil
from pathlib import Path
from inconsistency_resolver.parser import parse_mqxliff
from inconsistency_resolver.casebuilder import build_cases
from inconsistency_resolver.models import Decision
from inconsistency_resolver.apply import apply_decisions

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
```

- [ ] **Step 2: Run it; verify failure**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement apply**

`inconsistency_resolver/apply.py`:
```python
import re
import shutil
from lxml import etree
from xml.sax.saxutils import escape as _xml_escape
from .tags import detokenize

_XLIFF = "urn:oasis:names:tc:xliff:document:1.2"
_MQ = "MQXliff"

_TU_RE = re.compile(r"<trans-unit\b.*?</trans-unit>", re.DOTALL)
_TARGET_RE = re.compile(r"(<target\b[^>]*>)(.*?)(</target>)", re.DOTALL)


def _segguid(block: str):
    m = re.search(r'mq:segmentguid="([^"]+)"', block)
    return m.group(1) if m else None


def _set_target(block: str, new_inner: str) -> str:
    return _TARGET_RE.sub(lambda m: m.group(1) + new_inner + m.group(3), block, count=1)


def _mark_ignored(block: str) -> str:
    """Add the ignored attribute to inconsistency errorwarnings lacking it."""
    def repl(m):
        ew = m.group(0)
        if "inconsistent translation" not in ew:
            return ew
        if "errorwarning-ignored=" in ew:
            return ew
        return ew[:-2].rstrip() + ' mq:errorwarning-ignored="errorwarning-ignored" />'
    return re.sub(r"<mq:errorwarning\b[^>]*/>", repl, block)


def _remove_inconsistency_warnings(block: str) -> str:
    return re.sub(
        r'\s*<mq:errorwarning\b[^>]*mq:errorwarning-problemname="inconsistent translation"[^>]*/>',
        "", block)


def apply_decisions(in_path: str, decisions: dict, cases: list, out_path: str):
    shutil.copy(in_path, in_path + ".bak")

    with open(in_path, encoding="utf-8-sig", newline="") as fh:
        text = fh.read()

    case_by_id = {c.id: c for c in cases}

    # Map each segmentguid to the action to take on its block.
    # action: ("ignore",) | ("settarget", inner_xml) | ("remove_warn",)
    actions = {}
    skipped = []   # (case_id, tu_id, reason) for members we could not safely edit
    for cid, d in decisions.items():
        case = case_by_id.get(cid)
        if case is None or d.category == "needs_manual":
            continue
        if d.category == "false_positive":
            for m in case.members:
                actions[m.segmentguid] = ("ignore",)
        elif d.category == "pick_best":
            chosen = next((m for m in case.members if m.tu_id == d.chosen_member_id), None)
            if chosen is None:
                continue
            try:
                new_inner = detokenize(chosen.target_text, chosen.target_tags)
            except ValueError as exc:               # tag/token mismatch — never write broken XML
                skipped.append((cid, chosen.tu_id, str(exc)))
                continue
            for m in case.members:
                actions[m.segmentguid] = ("settarget", new_inner)
        elif d.category == "differentiate":
            wanted = {item["source_key"]: item["new_target"] for item in d.differentiated}
            for m in case.members:
                if m.source_text not in wanted:
                    continue
                try:
                    # _xml_escape the AI's plain-text target so a literal &/</> in
                    # the generated translation can't produce invalid XML. Markers
                    # (⟦N⟧) contain no special chars, so escaping is safe before
                    # detokenize, which still raises on a marker mismatch.
                    new_inner = detokenize(_xml_escape(wanted[m.source_text]), m.target_tags)
                except ValueError as exc:           # AI dropped/added a tag marker — skip this member
                    skipped.append((cid, m.tu_id, str(exc)))
                    continue
                actions[m.segmentguid] = ("settarget", new_inner)

    def edit_block(match):
        block = match.group(0)
        guid = _segguid(block)
        if guid not in actions:
            return block
        act = actions[guid]
        if act[0] == "ignore":
            return _mark_ignored(block)
        if act[0] == "settarget":
            block = _set_target(block, act[1])
            return _remove_inconsistency_warnings(block)
        return block

    new_text = _TU_RE.sub(edit_block, text)

    # Validate in memory BEFORE writing so a bad transform never lands on disk.
    etree.fromstring(new_text.encode("utf-8"))
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(new_text)
    return skipped


def _validate(path: str):
    """Re-parse to ensure well-formed XML; raise on failure."""
    etree.parse(path)
```

- [ ] **Step 4: Run apply tests; verify pass**

Run: `python -m pytest tests/test_apply.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/apply.py tests/test_apply.py
git commit -m "feat: apply decisions with targeted, format-preserving edits"
```

---

### Task 9: CLI (`analyze` and `apply`)

Wire everything into two subcommands. `analyze` runs the AI over all cases and writes the report; `apply` reads `decisions.json` and edits the file. `apply` honors `--include-low` and `--force`.

**Files:**
- Create: `inconsistency_resolver/cli.py`
- Create: `inconsistency_resolver/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import json
import shutil
from pathlib import Path
from inconsistency_resolver.cli import run_analyze, run_apply

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mqxliff"


class _Fake:
    """Returns false_positive for whitespace cases, differentiate otherwise."""
    class messages:
        @staticmethod
        def create(**kw):
            user = kw["messages"][0]["content"]
            if "whitespace" in user or "typo" in user:
                payload = {"category": "false_positive", "rationale": "ws", "confidence": "high"}
            elif "source_inconsistency" in user:
                payload = {"category": "pick_best", "rationale": "std", "confidence": "high",
                           "chosen_variant_key": "Εύκολο στον καθαρισμό"}
            else:
                payload = {"category": "differentiate", "rationale": "colors",
                           "confidence": "high",
                           "differentiated": [{"source_key": "Ocean Deep Sand",
                                               "new_target": "Ωκεανός Βαθιά Άμμος"}]}
            return type("M", (), {"content": [type("B", (), {"type": "text",
                        "text": json.dumps(payload)})()]})()


def test_analyze_then_apply(tmp_path):
    src = tmp_path / "in.mqxliff"
    shutil.copy(FIXTURE, src)
    out_dir = tmp_path / "out"
    run_analyze(str(src), str(out_dir), glossary_path=None,
                model="claude-opus-4-8", client=_Fake())
    assert (out_dir / "decisions.json").exists()
    assert (out_dir / "report.html").exists()

    fixed = tmp_path / "in.FIXED.mqxliff"
    run_apply(str(src), str(out_dir / "decisions.json"), str(fixed),
              include_low=False, force=True)
    text = fixed.read_text(encoding="utf-8-sig")
    assert 'mq:errorwarning-ignored="errorwarning-ignored"' in text
    assert "Ωκεανός Βαθιά Άμμος" in text
    assert text.count("Εύκολο στον καθαρισμό") == 2
```

- [ ] **Step 2: Run it; verify failure**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement the CLI**

`inconsistency_resolver/cli.py`:
```python
import argparse
import json
import os
import sys
from dataclasses import asdict

from .parser import parse_mqxliff
from .casebuilder import build_cases
from .context import build_case_payload
from .glossary import load_glossary
from .ai import classify_case, build_system_prompt
from .report import write_reports
from .apply import apply_decisions
from .models import Decision


def _make_client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def run_analyze(in_path, out_dir, glossary_path, model, client=None):
    client = client or _make_client()
    members = parse_mqxliff(in_path)
    cases = build_cases(members)
    glossary = load_glossary(glossary_path)
    gloss_text = "\n".join(f"{k} = {v}" for k, v in glossary.items())
    system_prompt = build_system_prompt(gloss_text)

    decisions = {}
    for case in cases:
        payload = build_case_payload(case, members, glossary)
        try:
            decisions[case.id] = classify_case(client, payload, system_prompt, model)
        except Exception as exc:  # isolate per-case failures
            decisions[case.id] = Decision(case.id, "needs_manual",
                                          f"AI/processing error: {exc}", "low")
    write_reports(cases, decisions, out_dir)
    print(f"Analyzed {len(cases)} cases -> {out_dir}/report.html, {out_dir}/decisions.json")
    return cases, decisions


def run_apply(in_path, decisions_path, out_path, include_low, force):
    if os.path.exists(out_path) and not force:
        raise SystemExit(f"{out_path} exists; use --force to overwrite.")
    members = parse_mqxliff(in_path)
    cases = build_cases(members)
    with open(decisions_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    decisions = {}
    skipped_low = 0
    for cid, d in raw.items():
        if d.get("confidence") == "low" and not include_low:
            skipped_low += 1
            continue
        decisions[cid] = Decision(
            case_id=d["case_id"], category=d["category"], rationale=d["rationale"],
            confidence=d["confidence"], chosen_member_id=d.get("chosen_member_id"),
            differentiated=d.get("differentiated", []),
        )
    skipped = apply_decisions(in_path, decisions, cases, out_path)
    print(f"Applied {len(decisions)} decisions -> {out_path}"
          + (f" ({skipped_low} low-confidence skipped)" if skipped_low else ""))
    for case_id, tu_id, reason in skipped:
        print(f"  WARNING: case {case_id} segment {tu_id} left unchanged (tag mismatch): {reason}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="inconsistency_resolver")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze")
    a.add_argument("input")
    a.add_argument("--out-dir", default="out")
    a.add_argument("--glossary", default=None)
    a.add_argument("--model", default="claude-opus-4-8")

    ap = sub.add_parser("apply")
    ap.add_argument("input")
    ap.add_argument("decisions")
    ap.add_argument("--out", default=None)
    ap.add_argument("--include-low", action="store_true")
    ap.add_argument("--force", action="store_true")

    args = p.parse_args(argv)
    if args.cmd == "analyze":
        run_analyze(args.input, args.out_dir, args.glossary, args.model)
    else:
        out = args.out or args.input.replace(".mqxliff", ".FIXED.mqxliff")
        run_apply(args.input, args.decisions, out, args.include_low, args.force)


if __name__ == "__main__":
    main(sys.argv[1:])
```

`inconsistency_resolver/__main__.py`:
```python
from .cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run CLI test; verify pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add inconsistency_resolver/cli.py inconsistency_resolver/__main__.py tests/test_cli.py
git commit -m "feat: analyze and apply CLI subcommands"
```

---

### Task 10: End-to-end dry run on the real file + acceptance

Run `analyze` against the real 12 MB file with a small case cap first (sanity), inspect the report, then a full run, then `apply`, then the manual memoQ acceptance test.

**Files:**
- Modify: `inconsistency_resolver/cli.py` (add optional `--limit` for a sanity subset)
- Test: `tests/test_cli.py` (add a limit test)

- [ ] **Step 1: Write the failing test for `--limit`**

Add to `tests/test_cli.py`:
```python
def test_analyze_limit_caps_cases(tmp_path):
    import shutil
    src = tmp_path / "in.mqxliff"
    shutil.copy(FIXTURE, src)
    out_dir = tmp_path / "out"
    cases, decisions = run_analyze(str(src), str(out_dir), None,
                                   "claude-opus-4-8", client=_Fake(), limit=1)
    assert len(decisions) == 1
```

- [ ] **Step 2: Run it; verify failure**

Run: `python -m pytest tests/test_cli.py::test_analyze_limit_caps_cases -v`
Expected: FAIL with `TypeError: run_analyze() got an unexpected keyword argument 'limit'`.

- [ ] **Step 3: Add `limit` support**

In `inconsistency_resolver/cli.py`, change `run_analyze` signature and case loop:
```python
def run_analyze(in_path, out_dir, glossary_path, model, client=None, limit=None):
    client = client or _make_client()
    members = parse_mqxliff(in_path)
    cases = build_cases(members)
    if limit:
        cases = cases[:limit]
    glossary = load_glossary(glossary_path)
    gloss_text = "\n".join(f"{k} = {v}" for k, v in glossary.items())
    system_prompt = build_system_prompt(gloss_text)

    decisions = {}
    for case in cases:
        payload = build_case_payload(case, members, glossary)
        try:
            decisions[case.id] = classify_case(client, payload, system_prompt, model)
        except Exception as exc:
            decisions[case.id] = Decision(case.id, "needs_manual",
                                          f"AI/processing error: {exc}", "low")
    write_reports(cases, decisions, out_dir)
    print(f"Analyzed {len(cases)} cases -> {out_dir}/report.html, {out_dir}/decisions.json")
    return cases, decisions
```
And add to the `analyze` subparser: `a.add_argument("--limit", type=int, default=None)` and pass `args.limit` in `main`.

- [ ] **Step 4: Run the limit test; verify pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Real-file sanity run (3 cases)**

Run:
```bash
cd "C:/Users/ada/Documents/Claude/Projects/QA resolvers/Inconsistency"
python -m inconsistency_resolver analyze check_gre.mqxliff --out-dir out --limit 3
```
Expected: `out/report.html` + `out/decisions.json` created; manually open the HTML and confirm the three cases look sensible (categories, rationales, segment numbers, diffs).

- [ ] **Step 6: Full analyze run**

Run:
```bash
python -m inconsistency_resolver analyze check_gre.mqxliff --out-dir out
```
Expected: all cases classified; review `out/report.html`. Confirm false-positive rationales name concrete differences and no `differentiate` target dropped a `⟦N⟧` marker.

- [ ] **Step 7: Apply**

Run:
```bash
python -m inconsistency_resolver apply check_gre.mqxliff out/decisions.json --force
```
Expected: `check_gre.FIXED.mqxliff` + `check_gre.mqxliff.bak`; console reports counts.

- [ ] **Step 8: Acceptance test (manual, user)**

Import `check_gre.FIXED.mqxliff` into memoQ, re-run QA. Expected: **zero `inconsistent translation` warnings remain** (false-positives now ignored, pick_best/differentiate now consistent). Record the result. If any remain, capture the segmentguids and feed back into a follow-up bugfix task — likely the round-trip/ignored-flag note in spec §8/§14.

- [ ] **Step 9: Commit**

```bash
git add inconsistency_resolver/cli.py tests/test_cli.py
git commit -m "feat: add --limit sanity flag and document e2e run"
```

---

## Self-Review

**Spec coverage check (spec → task):**
- §2 problem analysis (warning extraction, two directions) → Task 3 (parser warnings), Task 4 (case directions). ✓
- §2 memoQ ignore mechanism → Task 8 `_mark_ignored`. ✓
- §3 decision context (glossary, TM, frequency, neighbors) → Task 5 context (glossary, TM, frequency). *Neighbor segments* are mentioned in the spec but only frequency/TM/glossary are in the payload; neighbors are deferred — the dataset's cases are short attribute strings where neighbors add little. **Acceptable scope trim; noted here so it is a conscious omission, not a gap.** If the acceptance test (Task 10 §8) shows ambiguous cases needing surrounding context, add a neighbor field to `build_case_payload`.
- §7 AI contract (3 categories, structured output, tag tokens) → Task 6. ✓
- §8 write mechanics (pick_best copy XML, differentiate, false_positive ignore, backup, new file) → Task 8. ✓
- §9 report incl. false-positive transparency (segment numbers + mechanical diff + rationale) → Task 7. ✓
- §10 error handling (per-case isolation, tag/token mismatch rejection, low-confidence skip, idempotency, post-validate) → Task 6/`detokenize`, Task 8 `_validate`, Task 9 (`needs_manual`, `--include-low`, `--force`). ✓
- §11 tests (unit, golden fixture, manual acceptance) → Tasks 1-9 unit + `sample.mqxliff` golden + Task 10 §8 acceptance. ✓
- §12 CLI → Task 9. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete runnable code. ✓

**Type consistency:** `Member`/`Case`/`Decision` fields are used identically across parser, casebuilder, context, ai, report, apply, cli. `classify_case(client, payload, system_prompt, model)` signature matches its call in `run_analyze`. `apply_decisions(in_path, decisions, cases, out_path)` matches its calls in tests and `run_apply`. `detokenize(text, mapping)` matches Task 2. ✓

**Note on tag/token mismatch handling:** `detokenize` raises `ValueError` on mismatch; `apply_decisions` wraps each per-member detokenize in try/except → on failure the member is skipped (recorded in the returned `skipped` list) and never written, so a single mismatch can't abort the whole apply.

---

## Addendum: Target edge-whitespace normalization (Tasks 11–13)

Deterministic (no AI). Fixes targets whose leading/trailing `[ space/tab ]` run differs from the source's, setting the target edge whitespace equal to the source's. Scope: all segments. See spec §13a.

`decisions.json` format becomes: `{"whitespace_fixes": [ {tu_id, segmentguid, new_lead, new_trail, old_lead, old_trail}, ... ], "decisions": { case_id: {...}, ... }}`.

### Task 11: Whitespace module

**Files:**
- Create: `inconsistency_resolver/whitespace.py`
- Test: `tests/test_whitespace.py`

- [ ] **Step 1: Write the failing test**

`tests/test_whitespace.py`:
```python
from inconsistency_resolver.models import Member
from inconsistency_resolver.whitespace import (
    lead_ws, trail_ws, compute_ws_fixes, normalize_members,
)


def _m(tu_id, src, tgt):
    return Member(tu_id, "g" + tu_id, src, tgt, {}, {}, "Edited", None, [])


def test_edge_helpers():
    assert lead_ws("   ⟦1⟧x") == "   "
    assert trail_ws("x⟦1⟧   ") == "   "
    assert lead_ws("⟦1⟧x") == ""
    assert trail_ws("x") == ""


def test_compute_fix_only_when_edges_differ():
    members = [
        _m("1", "⟦1⟧Mattress:⟦2⟧", "          ⟦1⟧Στρώμα:⟦2⟧          "),  # 10/10 extra
        _m("2", "⟦1⟧X⟦2⟧", "⟦1⟧Υ⟦2⟧"),                                    # already clean
    ]
    fixes = compute_ws_fixes(members)
    assert len(fixes) == 1
    f = fixes[0]
    assert f["tu_id"] == "1"
    assert f["new_lead"] == "" and f["new_trail"] == ""
    assert f["old_lead"] == "          " and f["old_trail"] == "          "


def test_compute_fix_keeps_source_edges():
    # source HAS one trailing space -> target must end with exactly one space
    members = [_m("1", "X ", "Υ   ")]
    f = compute_ws_fixes(members)[0]
    assert f["new_trail"] == " " and f["new_lead"] == ""


def test_normalize_members_sets_target_edges_to_source():
    members = [_m("1", "⟦1⟧Mattress:⟦2⟧", "          ⟦1⟧Στρώμα:⟦2⟧          ")]
    normalize_members(members)
    assert members[0].target_text == "⟦1⟧Στρώμα:⟦2⟧"


def test_normalize_leaves_internal_and_nbsp_untouched():
    # internal spaces and a leading nbsp are NOT touched (only space/tab edges)
    members = [_m("1", "X", "\xa0Υ  Z")]   # source no edge ws; target leading nbsp + internal
    normalize_members(members)
    assert members[0].target_text == "\xa0Υ  Z"   # nbsp not space/tab -> unchanged
```

- [ ] **Step 2: Run; verify failure**

Run: `python -m pytest tests/test_whitespace.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`inconsistency_resolver/whitespace.py`:
```python
import re

_LEAD = re.compile(r'^[ \t]*')
_TRAIL = re.compile(r'[ \t]*$')


def lead_ws(text: str) -> str:
    return _LEAD.match(text).group(0)


def trail_ws(text: str) -> str:
    return _TRAIL.search(text).group(0)


def compute_ws_fixes(members: list) -> list:
    """Fixes for members whose target edge whitespace differs from source's."""
    fixes = []
    for m in members:
        s_lead, s_trail = lead_ws(m.source_text), trail_ws(m.source_text)
        t_lead, t_trail = lead_ws(m.target_text), trail_ws(m.target_text)
        if t_lead != s_lead or t_trail != s_trail:
            fixes.append({
                "tu_id": m.tu_id, "segmentguid": m.segmentguid,
                "new_lead": s_lead, "new_trail": s_trail,
                "old_lead": t_lead, "old_trail": t_trail,
            })
    return fixes


def normalize_members(members: list) -> list:
    """In place: set each target's edge whitespace equal to its source's."""
    for m in members:
        s_lead, s_trail = lead_ws(m.source_text), trail_ws(m.source_text)
        core = _TRAIL.sub("", _LEAD.sub("", m.target_text))
        m.target_text = s_lead + core + s_trail
    return members
```

- [ ] **Step 4: Run; verify pass; run full suite**

Run: `python -m pytest tests/test_whitespace.py -v` → PASS (5). Then `python -m pytest -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/whitespace.py tests/test_whitespace.py
git commit -m "feat: deterministic target edge-whitespace normalization module"
```

---

### Task 12: Wire normalization into report + analyze (new decisions.json format)

**Files:**
- Modify: `inconsistency_resolver/report.py`
- Modify: `inconsistency_resolver/cli.py` (`run_analyze`)
- Test: `tests/test_report.py` (add ws section test), `tests/test_cli.py` (update for new format)

- [ ] **Step 1: Update `write_reports` to accept and render whitespace fixes**

Change the signature to `write_reports(cases, decisions, out_dir, ws_fixes=None)`. Write `decisions.json` in the new nested format and add a whitespace section + summary to the HTML.

Replace `report.py` with:
```python
import json
import html
import os
from collections import Counter
from dataclasses import asdict


def write_reports(cases, decisions, out_dir, ws_fixes=None):
    ws_fixes = ws_fixes or []
    os.makedirs(out_dir, exist_ok=True)
    _write_json(decisions, ws_fixes, os.path.join(out_dir, "decisions.json"))
    _write_html(cases, decisions, ws_fixes, os.path.join(out_dir, "report.html"))


def _write_json(decisions, ws_fixes, path):
    data = {
        "whitespace_fixes": ws_fixes,
        "decisions": {cid: asdict(d) for cid, d in decisions.items()},
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _esc(s):
    return html.escape(str(s))


def _vis(ws):
    """Visualize a whitespace run: '' -> '(none)', '   ' -> '·×3'."""
    return "(none)" if ws == "" else f"·×{len(ws)}"


def _write_html(cases, decisions, ws_fixes, path):
    counts = Counter(d.category for d in decisions.values())
    case_by_id = {c.id: c for c in cases}

    rows = []
    for cid, d in decisions.items():
        c = case_by_id.get(cid)
        seg_ids = ", ".join(m.tu_id for m in c.members) if c else ""
        sources = "<br>".join(_esc(s) for s in sorted(c.distinct_sources)) if c else ""
        targets = "<br>".join(_esc(t) for t in sorted(c.distinct_targets)) if c else ""
        diff = _esc(c.mechanical_diff) if c else ""
        rows.append(f"""
        <tr class="{_esc(d.category)}">
          <td>{_esc(cid)}</td>
          <td>{_esc(d.category)}</td>
          <td>{_esc(d.confidence)}</td>
          <td>{seg_ids}</td>
          <td><b>diff:</b> {diff}<br><b>sources:</b><br>{sources}<br>
              <b>targets:</b><br>{targets}</td>
          <td>{_esc(d.rationale)}</td>
        </tr>""")

    ws_rows = []
    for f in ws_fixes:
        ws_rows.append(f"""
        <tr><td>{_esc(f['tu_id'])}</td>
            <td>lead: {_vis(f['old_lead'])} &rarr; {_vis(f['new_lead'])}</td>
            <td>trail: {_vis(f['old_trail'])} &rarr; {_vis(f['new_trail'])}</td></tr>""")

    summary = " &nbsp; ".join(f"{cat}: {n}" for cat, n in sorted(counts.items()))
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Inconsistency Resolver Report</title>
<style>
 body{{font-family:sans-serif;margin:2rem}}
 table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
 td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;font-size:13px}}
 tr.false_positive{{background:#f3faf3}}
 tr.differentiate{{background:#fff6e6}}
 tr.pick_best{{background:#eef3fb}}
 tr.needs_manual{{background:#fdecec}}
</style></head><body>
<h1>Inconsistency Resolver Report</h1>
<p><b>Decisions summary:</b> {summary}</p>
<p><b>Whitespace fixes (target edge = source edge):</b> {len(ws_fixes)}</p>
<h2>Whitespace fixes</h2>
<table>
<tr><th>Segment</th><th>Leading</th><th>Trailing</th></tr>
{''.join(ws_rows)}
</table>
<h2>Inconsistency decisions</h2>
<table>
<tr><th>Case</th><th>Category</th><th>Confidence</th><th>Segments</th>
    <th>Diff / Sources / Targets</th><th>Rationale</th></tr>
{''.join(rows)}
</table></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
```

- [ ] **Step 2: Update the existing report tests for the new JSON shape**

In `tests/test_report.py`, the JSON now nests decisions under `"decisions"`. Update `test_writes_json_and_html`:
```python
def test_writes_json_and_html(tmp_path):
    cases, decisions = _case_and_decision()
    write_reports(cases, decisions, str(tmp_path), ws_fixes=[
        {"tu_id": "9", "segmentguid": "g9", "new_lead": "", "new_trail": "",
         "old_lead": "          ", "old_trail": "          "}])
    data = json.loads((tmp_path / "decisions.json").read_text(encoding="utf-8"))
    assert data["decisions"]["T1"]["category"] == "false_positive"
    assert len(data["whitespace_fixes"]) == 1
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "T1" in html
    assert "trailing space" in html
    assert "whitespace" in html.lower()
    assert "·×10" in html                       # whitespace fix visualized
```
Keep `test_summary_counts` but change its assertion to look for the decisions summary, e.g. `assert "false_positive: 1" in html`.

- [ ] **Step 3: Update `run_analyze` to compute fixes, normalize, and pass them through**

In `inconsistency_resolver/cli.py`, add imports and rework `run_analyze`:
```python
from .whitespace import compute_ws_fixes, normalize_members
```
```python
def run_analyze(in_path, out_dir, glossary_path, model, client=None, limit=None):
    client = client or _make_client()
    members = parse_mqxliff(in_path)
    ws_fixes = compute_ws_fixes(members)        # detect BEFORE normalizing
    normalize_members(members)                  # collapse pure edge-ws inconsistencies
    cases = build_cases(members)
    if limit:
        cases = cases[:limit]
    glossary = load_glossary(glossary_path)
    gloss_text = "\n".join(f"{k} = {v}" for k, v in glossary.items())
    system_prompt = build_system_prompt(gloss_text)

    decisions = {}
    for case in cases:
        payload = build_case_payload(case, members, glossary)
        try:
            decisions[case.id] = classify_case(client, payload, system_prompt, model)
        except Exception as exc:
            decisions[case.id] = Decision(case.id, "needs_manual",
                                          f"AI/processing error: {exc}", "low")
    write_reports(cases, decisions, out_dir, ws_fixes=ws_fixes)
    print(f"Analyzed {len(cases)} cases, {len(ws_fixes)} whitespace fixes "
          f"-> {out_dir}/report.html, {out_dir}/decisions.json")
    return cases, decisions, ws_fixes
```
Note the return is now a 3-tuple. Update `tests/test_cli.py` accordingly (the analyze→apply test and the `--limit` test unpack three values; the limit test asserts `len(decisions) == 1`).

- [ ] **Step 4: Run full suite**

Run: `python -m pytest -q`. Fix any test that still assumes the old shapes (only the report and cli tests should need updates). Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add inconsistency_resolver/report.py inconsistency_resolver/cli.py tests/test_report.py tests/test_cli.py
git commit -m "feat: surface whitespace fixes in report and new decisions.json format"
```

---

### Task 13: Apply whitespace fixes

**Files:**
- Modify: `inconsistency_resolver/apply.py`
- Modify: `inconsistency_resolver/cli.py` (`run_apply`)
- Test: `tests/test_apply.py` (add ws tests), `tests/test_cli.py` (end-to-end still passes)

- [ ] **Step 1: Write failing apply tests**

Add to `tests/test_apply.py`:
```python
def test_whitespace_fix_trims_target_edges(tmp_path):
    import shutil
    src = tmp_path / "in.mqxliff"; shutil.copy(FIXTURE, src)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    # tu1 target is "Κουτί χρώματος:" (no edge ws in fixture) -> craft a fix that
    # would prepend then we assert it is applied verbatim to the raw <target> edges.
    ws_fixes = [{"tu_id": "1", "segmentguid": "g1",
                 "new_lead": "", "new_trail": " ", "old_lead": "", "old_trail": ""}]
    apply_decisions(str(src), {}, cases, str(out), ws_fixes=ws_fixes)
    text = out.read_text(encoding="utf-8-sig")
    # tu g1's target now ends with exactly one space before </target>
    import re
    m = re.search(r'segmentguid="g1".*?<target[^>]*>(.*?)</target>', text, re.S)
    assert m.group(1).endswith("χρώματος: ")


def test_whitespace_fix_and_ignore_coexist(tmp_path):
    import shutil
    src = tmp_path / "in.mqxliff"; shutil.copy(FIXTURE, src)
    out = tmp_path / "out.mqxliff"
    cases = build_cases(parse_mqxliff(str(src)))
    kouti = [c for c in cases if c.type == "target_inconsistency"
             and "Κουτί" in next(iter(c.distinct_targets))][0]
    from inconsistency_resolver.models import Decision
    decisions = {kouti.id: Decision(kouti.id, "false_positive", "ws", "high")}
    ws_fixes = [{"tu_id": "1", "segmentguid": "g1",
                 "new_lead": "", "new_trail": "", "old_lead": "", "old_trail": ""}]
    skipped = apply_decisions(str(src), decisions, cases, str(out), ws_fixes=ws_fixes)
    text = out.read_text(encoding="utf-8-sig")
    assert 'mq:errorwarning-ignored="errorwarning-ignored"' in text
```

- [ ] **Step 2: Run; verify failure** (`apply_decisions` has no `ws_fixes` param yet).

- [ ] **Step 3: Implement in `apply.py`**

Add a helper and extend `apply_decisions`:
```python
def _trim_target_edges(block: str, new_lead: str, new_trail: str) -> str:
    def repl(m):
        inner = m.group(2)
        inner = re.sub(r'^[ \t]*', new_lead, inner)
        inner = re.sub(r'[ \t]*$', new_trail, inner)
        return m.group(1) + inner + m.group(3)
    return _TARGET_RE.sub(repl, block, count=1)
```
Change the signature to `def apply_decisions(in_path, decisions, cases, out_path, ws_fixes=None):`. Build `ws_by_guid = {f["segmentguid"]: (f["new_lead"], f["new_trail"]) for f in (ws_fixes or [])}`. Then replace `edit_block` with:
```python
    def edit_block(match):
        block = match.group(0)
        guid = _segguid(block)
        act = actions.get(guid)
        # settarget already carries normalized edges (members were normalized
        # before case-building), so it supersedes any separate ws trim.
        if act and act[0] == "settarget":
            block = _set_target(block, act[1])
            return _remove_inconsistency_warnings(block)
        if guid in ws_by_guid:
            block = _trim_target_edges(block, *ws_by_guid[guid])
        if act and act[0] == "ignore":
            block = _mark_ignored(block)
        return block
```
Leave the rest (backup, write, `_validate`, `return skipped`) unchanged.

- [ ] **Step 4: Update `run_apply` to read the new format and pass ws_fixes**

In `inconsistency_resolver/cli.py` `run_apply`, replace the JSON load + apply portion:
```python
    with open(decisions_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    # new format: {"whitespace_fixes": [...], "decisions": {...}}; fall back to flat
    ws_fixes = raw.get("whitespace_fixes", []) if isinstance(raw, dict) else []
    raw_decisions = raw.get("decisions", raw) if isinstance(raw, dict) else raw

    decisions = {}
    skipped_low = 0
    for cid, d in raw_decisions.items():
        if d.get("confidence") == "low" and not include_low:
            skipped_low += 1
            continue
        decisions[cid] = Decision(
            case_id=d["case_id"], category=d["category"], rationale=d["rationale"],
            confidence=d["confidence"], chosen_member_id=d.get("chosen_member_id"),
            differentiated=d.get("differentiated", []),
        )
    skipped = apply_decisions(in_path, decisions, cases, out_path, ws_fixes=ws_fixes)
    print(f"Applied {len(decisions)} decisions, {len(ws_fixes)} whitespace fixes -> {out_path}"
          + (f" ({skipped_low} low-confidence skipped)" if skipped_low else ""))
    for case_id, tu_id, reason in skipped:
        print(f"  WARNING: case {case_id} segment {tu_id} left unchanged (tag mismatch): {reason}")
```
Note: `raw_decisions` keys whose decision references `chosen_member_id` still work because `run_apply` rebuilds `cases` from the (re-parsed + re-normalized?) file. **Important:** `run_apply` must also normalize members before `build_cases` so case ids match those in `decisions.json`. Add the same two lines used in analyze right after parsing in `run_apply`:
```python
    members = parse_mqxliff(in_path)
    from .whitespace import normalize_members
    normalize_members(members)
    cases = build_cases(members)
```
(If `run_apply` currently calls `build_cases(parse_mqxliff(in_path))` inline, refactor to the three lines above so the case ids are deterministic and identical to the analyze run.)

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`. Expected: all green (including the existing end-to-end CLI test, which now also carries `ws_fixes=[]` through the pipeline).

- [ ] **Step 6: Commit**

```bash
git add inconsistency_resolver/apply.py inconsistency_resolver/cli.py tests/test_apply.py tests/test_cli.py
git commit -m "feat: apply target edge-whitespace fixes alongside AI decisions"
```

---

### Task 14: Re-verify end-to-end on the real file (no API)

- [ ] **Step 1:** Run a no-API sanity to confirm the case count drops and whitespace fixes are detected:
```bash
python -c "from inconsistency_resolver.parser import parse_mqxliff; from inconsistency_resolver.whitespace import compute_ws_fixes, normalize_members; from inconsistency_resolver.casebuilder import build_cases; m=parse_mqxliff('check_gre.mqxliff'); f=compute_ws_fixes(m); normalize_members(m); print('ws_fixes', len(f), 'cases', len(build_cases(m)))"
```
Observed: **692 whitespace fixes**; case count **unchanged at 102**. (The edge-whitespace defects sit on heavily-repeated boilerplate segments that each carry a warning but have identical source+target, so they don't form inconsistency *cases* — they're handled purely as deterministic ws-fixes. A case only collapses when normalization makes a same-source pair's targets identical, and there were 0 source-inconsistency cases here.) Both numbers recorded.
- [ ] **Step 2:** Commit nothing (verification only). The paid `analyze` run + memoQ acceptance remain the user's step.

---

## Addendum 2: Full tag-boundary whitespace alignment (Task 15) — supersedes edge-only

Real-file finding: **815 segments** have spurious `[ \t]` spaces *around inline tags* in the target that the source lacks (not just at the very edges) — e.g. source `⟦1⟧⟦2⟧Perfect Size⟦3⟧⟦4⟧`, target `⟦1⟧ ⟦2⟧ Ιδανικό Μέγεθος ⟦3⟧ ⟦4⟧`. Only 1 segment has a source/target marker-count mismatch. Generalize the normalizer: align each inter-tag **text run's** leading/trailing `[ \t]` to the source's. This preserves inter-word spaces and `nbsp`, touches only whitespace adjacent to tags, and naturally includes the edges (so it replaces Task 11's edge-only logic). Skip any segment whose source/target marker counts differ.

The `whitespace_fixes` entry shape changes to `{tu_id, segmentguid, new_target_inner, old_preview, new_preview}` where `new_target_inner` is the realigned RAW target inner-XML (apply writes it whole, like `settarget`).

### Task 15: Replace edge-only normalization with tag-boundary alignment

**Files:**
- Modify: `inconsistency_resolver/whitespace.py`
- Modify: `inconsistency_resolver/apply.py`
- Modify: `inconsistency_resolver/report.py`
- Test: `tests/test_whitespace.py`, `tests/test_apply.py`, `tests/test_report.py`

- [ ] **Step 1: Rewrite `inconsistency_resolver/whitespace.py`**
```python
import re
from .tags import detokenize

_MARK = re.compile(r'⟦\d+⟧')
_LEAD = re.compile(r'^[ \t]*')
_TRAIL = re.compile(r'[ \t]*$')


def lead_ws(text: str) -> str:
    return _LEAD.match(text).group(0)


def trail_ws(text: str) -> str:
    return _TRAIL.search(text).group(0)


def _split(tok: str):
    """(text_parts[n+1], markers[n]) for a tokenized string."""
    return _MARK.split(tok), _MARK.findall(tok)


def align_whitespace(src_tok: str, tgt_tok: str) -> str:
    """Set each inter-tag text run's leading/trailing [ \\t] in the target equal
    to the source's corresponding run. Returns the target unchanged when the
    marker counts differ (cannot safely align). Inter-word spaces and non-[ \\t]
    characters (e.g. nbsp) are preserved."""
    s_parts, s_marks = _split(src_tok)
    t_parts, t_marks = _split(tgt_tok)
    if len(s_marks) != len(t_marks):
        return tgt_tok
    new_parts = []
    for i, t in enumerate(t_parts):
        s = s_parts[i]
        core = _TRAIL.sub('', _LEAD.sub('', t))
        new_parts.append(lead_ws(s) + core + trail_ws(s))
    out = new_parts[0]
    for mk, part in zip(t_marks, new_parts[1:]):
        out += mk + part
    return out


def compute_ws_fixes(members: list) -> list:
    """Fixes for members whose target whitespace doesn't match the source's
    tag-boundary whitespace."""
    fixes = []
    for m in members:
        new_tok = align_whitespace(m.source_text, m.target_text)
        if new_tok != m.target_text:
            fixes.append({
                "tu_id": m.tu_id,
                "segmentguid": m.segmentguid,
                "new_target_inner": detokenize(new_tok, m.target_tags),
                "old_preview": m.target_text,
                "new_preview": new_tok,
            })
    return fixes


def normalize_members(members: list) -> list:
    """In place: align each target's tag-boundary whitespace to its source's."""
    for m in members:
        m.target_text = align_whitespace(m.source_text, m.target_text)
    return members
```

- [ ] **Step 2: Rewrite `tests/test_whitespace.py`**
```python
from inconsistency_resolver.models import Member
from inconsistency_resolver.whitespace import (
    lead_ws, trail_ws, align_whitespace, compute_ws_fixes, normalize_members,
)


def _m(tu_id, src, tgt, tags=None):
    return Member(tu_id, "g" + tu_id, src, tgt, {}, tags or {}, "Edited", None, [])


def test_edge_helpers():
    assert lead_ws("   ⟦1⟧x") == "   "
    assert trail_ws("x⟦1⟧   ") == "   "
    assert lead_ws("⟦1⟧x") == ""


def test_align_removes_tag_adjacent_spaces():
    src = "⟦1⟧⟦2⟧Perfect Size⟦3⟧⟦4⟧"
    tgt = "⟦1⟧ ⟦2⟧ Ιδανικό Μέγεθος ⟦3⟧ ⟦4⟧"
    assert align_whitespace(src, tgt) == "⟦1⟧⟦2⟧Ιδανικό Μέγεθος⟦3⟧⟦4⟧"


def test_align_keeps_source_boundary_spaces():
    src = "⟦1⟧ Perfect Size ⟦2⟧"      # source HAS a space inside the tags
    tgt = "⟦1⟧Ιδανικό Μέγεθος⟦2⟧"
    assert align_whitespace(src, tgt) == "⟦1⟧ Ιδανικό Μέγεθος ⟦2⟧"


def test_align_preserves_internal_and_edges():
    src = "⟦1⟧Mattress:⟦2⟧"
    tgt = "          ⟦1⟧Στρώμα:⟦2⟧          "   # leading+trailing edge ws
    assert align_whitespace(src, tgt) == "⟦1⟧Στρώμα:⟦2⟧"


def test_align_skips_on_marker_count_mismatch():
    src = "⟦1⟧X"
    tgt = "⟦1⟧ Υ ⟦2⟧"                 # extra marker -> cannot align
    assert align_whitespace(src, tgt) == tgt   # unchanged


def test_align_leaves_nbsp_untouched():
    src = "⟦1⟧X⟦2⟧"
    tgt = "⟦1⟧\xa0Υ\xa0⟦2⟧"           # nbsp adjacent to tags, not [ \t]
    assert align_whitespace(src, tgt) == tgt


def test_compute_fixes_shape_and_detokenize():
    tags = {"⟦1⟧": '<ph id="1"/>'}
    members = [_m("1", "⟦1⟧Mattress:", "   ⟦1⟧Στρώμα:", tags=tags)]
    fixes = compute_ws_fixes(members)
    assert len(fixes) == 1
    f = fixes[0]
    assert f["tu_id"] == "1"
    assert f["new_target_inner"] == '<ph id="1"/>Στρώμα:'   # markers restored, ws fixed
    assert f["new_preview"] == "⟦1⟧Στρώμα:"


def test_normalize_members_in_place():
    members = [_m("1", "⟦1⟧⟦2⟧X⟦3⟧", "⟦1⟧ ⟦2⟧ Υ ⟦3⟧")]
    normalize_members(members)
    assert members[0].target_text == "⟦1⟧⟦2⟧Υ⟦3⟧"
```

- [ ] **Step 3: Run whitespace tests** — `python -m pytest tests/test_whitespace.py -v` → all pass.

- [ ] **Step 4: Update `apply.py`** — ws fixes now set the whole target inner. In `apply_decisions` build `ws_by_guid = {f["segmentguid"]: f["new_target_inner"] for f in (ws_fixes or [])}`. Replace the `_trim_target_edges` use in `edit_block` with `_set_target`, and delete the now-unused `_trim_target_edges`:
```python
    def edit_block(match):
        block = match.group(0)
        guid = _segguid(block)
        act = actions.get(guid)
        if act and act[0] == "settarget":
            block = _set_target(block, act[1])
            return _remove_inconsistency_warnings(block)
        if guid in ws_by_guid:
            block = _set_target(block, ws_by_guid[guid])
        if act and act[0] == "ignore":
            block = _mark_ignored(block)
        return block
```

- [ ] **Step 5: Update the apply ws tests** in `tests/test_apply.py` to the new fix shape (use `new_target_inner` instead of `new_lead`/`new_trail`):
```python
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
    from inconsistency_resolver.models import Decision
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
```

- [ ] **Step 6: Update `report.py` whitespace rendering** — render before/after previews instead of edge viz. Replace the `ws_rows` builder and the `_vis` helper usage:
```python
    ws_rows = []
    for f in ws_fixes:
        ws_rows.append(f"""
        <tr><td>{_esc(f['tu_id'])}</td>
            <td><code>{_esc(f['old_preview'])}</code></td>
            <td><code>{_esc(f['new_preview'])}</code></td></tr>""")
```
and the whitespace table header to `<tr><th>Segment</th><th>Before</th><th>After</th></tr>`. Remove the now-unused `_vis` function.

- [ ] **Step 7: Update `tests/test_report.py`** ws assertion — the fix dict now has `old_preview`/`new_preview`; assert the after-preview text appears in the HTML instead of `·×10`:
```python
    write_reports(cases, decisions, str(tmp_path), ws_fixes=[
        {"tu_id": "9", "segmentguid": "g9",
         "new_target_inner": "Στρώμα:", "old_preview": "   ⟦1⟧Στρώμα:", "new_preview": "⟦1⟧Στρώμα:"}])
    ...
    assert "⟦1⟧Στρώμα:" in html        # after-preview rendered
```

- [ ] **Step 8: Run full suite** — `python -m pytest -q` → all green.

- [ ] **Step 9: No-API real-file check** —
```bash
python -c "from inconsistency_resolver.parser import parse_mqxliff; from inconsistency_resolver.whitespace import compute_ws_fixes; print('ws fixes:', len(compute_ws_fixes(parse_mqxliff('check_gre.mqxliff'))))"
```
Expected ≈ 815 (the tag-boundary cases). Record it.

- [ ] **Step 10: Commit**
```bash
git add inconsistency_resolver/whitespace.py inconsistency_resolver/apply.py inconsistency_resolver/report.py tests/test_whitespace.py tests/test_apply.py tests/test_report.py
git commit -m "feat: align target tag-boundary whitespace to source (supersedes edge-only)"
```
