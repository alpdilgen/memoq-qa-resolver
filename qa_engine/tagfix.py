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
from .tags import tag_label
from .taginv import tag_multiset

TAG_STRUCTURE_CODES = {"2010", "2011", "2015", "2016"}
_ID_RE = re.compile(r'(\bid=")[^"]*(")')


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


def _missing_self_contained_adds(member):
    """List of source tag XMLs (renumbered) to append so the target reaches tag
    count parity, or None if it cannot be done safely (paired or extra tags)."""
    src_ms = tag_multiset(member.source_text)
    tgt_ms = tag_multiset(member.target_text)
    missing = src_ms - tgt_ms
    extra = tgt_ms - src_ms
    if extra or not missing:
        return None
    adds, next_id = [], 9001
    for kind, n in missing.items():
        instances = [xml for _, xml in member.source_tags.items()
                     if tag_label(xml) == kind]
        if len(instances) < n or not all(_self_contained(x) for x in instances[:n]):
            return None
        for xml in instances[:n]:
            adds.append(_renumber(xml, next_id))
            next_id += 1
    return adds


def plan_tag_structure(member, tag_codes):
    """Deterministic plan for a segment's tag-structure codes.

    Returns (ignore_codes, additions_xml, remaining_codes):
      - ignore_codes: tag codes that are false positives (e.g. 2016 with tag parity)
      - additions_xml: source tag XML to append to the target inner (2011 self-contained)
      - remaining_codes: tag codes that cannot be safely auto-resolved -> human
    """
    codes = {_norm(c) for c in tag_codes}
    ignore_codes, additions, remaining = [], [], []
    parity = tag_multiset(member.source_text) == tag_multiset(member.target_text)

    for code in sorted(codes):
        if code == "2016":
            (ignore_codes if parity else remaining).append("2016")
        elif code == "2011":
            adds = _missing_self_contained_adds(member)
            if adds is not None:
                additions.extend(adds)
            else:
                remaining.append("2011")
        else:                       # 2010, 2015
            remaining.append(code)
    return ignore_codes, additions, remaining
