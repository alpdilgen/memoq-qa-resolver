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
    """Add the ignored attribute to every errorwarning on the segment that lacks it."""
    def repl(m):
        ew = m.group(0)
        if "errorwarning-ignored=" in ew:
            return ew
        return ew[:-2].rstrip() + ' mq:errorwarning-ignored="errorwarning-ignored" />'
    return re.sub(r"<mq:errorwarning\b[^>]*/>", repl, block)


def _remove_inconsistency_warnings(block: str) -> str:
    return re.sub(
        r'\s*<mq:errorwarning\b[^>]*mq:errorwarning-problemname="inconsistent translation"[^>]*/>',
        "", block)


def apply_decisions(in_path: str, decisions: dict, cases: list, out_path: str, ws_fixes=None):
    shutil.copy(in_path, in_path + ".bak")

    with open(in_path, encoding="utf-8-sig", newline="") as fh:
        text = fh.read()

    case_by_id = {c.id: c for c in cases}
    ws_by_guid = {f["segmentguid"]: f["new_target_inner"] for f in (ws_fixes or [])}

    # Map each segmentguid to the action to take on its block.
    # action: ("ignore",) | ("settarget", inner_xml) | ("remove_warn",)
    actions = {}
    skipped = []
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
            except ValueError as exc:
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
                    new_inner = detokenize(_xml_escape(wanted[m.source_text]), m.target_tags)
                except ValueError as exc:
                    skipped.append((cid, m.tu_id, str(exc)))
                    continue
                actions[m.segmentguid] = ("settarget", new_inner)

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
            block = _set_target(block, ws_by_guid[guid])
        if act and act[0] == "ignore":
            block = _mark_ignored(block)
        return block

    new_text = _TU_RE.sub(edit_block, text)

    etree.fromstring(new_text.encode("utf-8"))

    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(new_text)

    return skipped


def apply_resolved_items(content: bytes, items) -> bytes:
    """Apply a list of ResolvedItem to the mqxliff bytes. action == 'fix' sets the
    target inner (and removes that segment's inconsistency warning); action ==
    'ignore' marks the segment's inconsistency warnings ignored; 'report' is skipped."""
    text = content.decode("utf-8-sig")
    by_guid = {}   # segmentguid -> ("settarget", inner) | ("ignore",)
    # First pass: fixes win.
    for it in items:
        if it.resolution.action == "fix" and it.resolution.new_target is not None:
            new_target = it.resolution.new_target
            # Safety net: internal tokenisation markers must never be written as
            # literal text. Tokens are ⟦id:label⟧; the ⟦/⟧ delimiters are what we
            # guard on. If they slipped through upstream, skip this segment
            # entirely so the original target is preserved untouched.
            if "⟦" in new_target or "⟧" in new_target:
                continue
            by_guid[it.segmentguid] = ("settarget", new_target)
    # Second pass: ignore only where there is no fix.
    for it in items:
        if it.resolution.action == "ignore" and it.segmentguid not in by_guid:
            by_guid[it.segmentguid] = ("ignore",)

    def edit_block(match):
        block = match.group(0)
        guid = _segguid(block)
        act = by_guid.get(guid)
        if not act:
            return block
        if act[0] == "settarget":
            block = _set_target(block, act[1])
            return _remove_inconsistency_warnings(block)
        if act[0] == "ignore":
            return _mark_ignored(block)
        return block

    new_text = _TU_RE.sub(edit_block, text)
    etree.fromstring(new_text.encode("utf-8"))     # validate before returning
    return new_text.encode("utf-8-sig")
