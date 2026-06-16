"""Deterministic tag-structure resolution (codes 2010/2011/2015/2016).

User rules:
  - 2016 (order changed): tag multisets equal -> false positive (the target language
    may legitimately reorder tags). Mark that code ignored; never reorder, never add tags.
  - 2011 (missing tag): reach COUNT PARITY with the source by re-adding the missing
    tags. Exact placement doesn't matter for structural tags; only the count does.
    Only self-contained tags (ph / x / mq:ch — no open/close pairing) are auto-added;
    paired tags (bpt/ept/g) are left for a human.
  - 2015 (extra) / 2010 (malformed): left for a human (cannot guarantee safe auto-fix).

Added tags are re-numbered to high, unused memoQ ids so they never collide with the
target's existing tag ids.
"""
import re
from .tags import tag_label, detokenize, _TOKEN_RE
from .taginv import tag_multiset

TAG_STRUCTURE_CODES = {"2010", "2011", "2015", "2016"}
_ID_RE = re.compile(r'(\bid=")[^"]*(")')


def _kind_of(token: str) -> str:
    """Kind (readable label) of a ⟦id:label⟧ token, e.g. ⟦12:<ph>⟧ -> '<ph>'."""
    return token[token.index(":") + 1:-1]


def _kinds(tok_text: str):
    return [_kind_of(m.group(0)) for m in _TOKEN_RE.finditer(tok_text or "")]


def _norm(c):
    try:
        return str(int(c))
    except (TypeError, ValueError):
        return c or ""


def _self_contained(xml: str) -> bool:
    s = xml.lstrip()
    return s.startswith("<ph") or s.startswith("<x") or s.startswith("<mq:ch")


def _renumber(xml: str, new_id: int) -> str:
    return _ID_RE.sub(lambda m: f"{m.group(1)}{new_id}{m.group(2)}", xml, count=1)


def _build_ordered_target(member):
    """Corrected target XML for a 2011 (missing-tag) segment: the missing tags are
    re-inserted in their SOURCE-relative ORDER (not appended at the end — appending
    fixes the count but trips memoQ's 2016 order check). Returns the XML, or None
    when it can't be done safely (extra tags, paired/non-self-contained missing
    tags, or the target's tag order isn't a subsequence of the source's)."""
    src_ms = tag_multiset(member.source_text)
    tgt_ms = tag_multiset(member.target_text)
    missing = src_ms - tgt_ms
    extra = tgt_ms - src_ms
    if extra or not missing:
        return None

    by_kind = {}
    for _, xml in member.source_tags.items():
        by_kind.setdefault(tag_label(xml), []).append(xml)
    for kind, n in missing.items():
        inst = by_kind.get(kind, [])
        if len(inst) < n or not all(_self_contained(x) for x in inst[:n]):
            return None

    src_kinds = _kinds(member.source_text)
    tgt_tokens = list(_TOKEN_RE.finditer(member.target_text))
    tgt_kinds = [_kind_of(t.group(0)) for t in tgt_tokens]

    # Walk the source tag order; matched kinds advance the target pointer, missing
    # ones record an insertion before the current target marker index. Consume
    # source instances in order so inserts carry the actually-missing instances.
    inserts, sp, t = {}, {}, 0
    for sk in src_kinds:
        pool = by_kind.get(sk, [])
        if sp.get(sk, 0) >= len(pool):
            return None   # label/instance mismatch -> don't risk it, leave to a human
        xml = pool[sp.get(sk, 0)]
        sp[sk] = sp.get(sk, 0) + 1
        if t < len(tgt_kinds) and tgt_kinds[t] == sk:
            t += 1
        else:
            inserts.setdefault(t, []).append(xml)
    if t != len(tgt_kinds):
        return None  # target order isn't a subsequence of source -> not safe to splice

    ext_map = dict(member.target_tags)
    next_id = 9001
    text, out, pos = member.target_text, [], 0

    def _emit_inserts(idx):
        nonlocal next_id
        for xml in inserts.get(idx, []):
            ext_map[str(next_id)] = _renumber(xml, next_id)
            out.append(f"⟦{next_id}:{tag_label(xml)}⟧")
            next_id += 1

    for idx, mt in enumerate(tgt_tokens):
        out.append(text[pos:mt.start()])
        _emit_inserts(idx)
        out.append(mt.group(0))
        pos = mt.end()
    out.append(text[pos:])
    _emit_inserts(len(tgt_tokens))

    try:
        return detokenize("".join(out), ext_map)
    except ValueError:
        return None


def plan_tag_structure(member, tag_codes):
    """Deterministic plan for a segment's tag-structure codes.

    Returns (ignore_codes, new_target_xml, remaining_codes):
      - ignore_codes: tag codes that are false positives (e.g. 2016 with tag parity)
      - new_target_xml: corrected target inner XML when a 2011 fix could be built
        (missing tags inserted in source order), else None
      - remaining_codes: tag codes that cannot be safely auto-resolved -> human
    """
    codes = {_norm(c) for c in tag_codes}
    ignore_codes, new_target_xml, remaining = [], None, []
    parity = tag_multiset(member.source_text) == tag_multiset(member.target_text)

    for code in sorted(codes):
        if code == "2016":
            (ignore_codes if parity else remaining).append("2016")
        elif code == "2011":
            built = _build_ordered_target(member)
            if built is not None:
                new_target_xml = built
            else:
                remaining.append("2011")
        else:                       # 2010, 2015
            remaining.append(code)
    return ignore_codes, new_target_xml, remaining
