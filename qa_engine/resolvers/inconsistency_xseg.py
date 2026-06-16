"""Cross-segment inconsistency (3100/3101) resolution — Phase A.

Inconsistency is inherently a cross-segment problem: the same source rendered
differently across the document. A per-segment pass cannot fix it (each segment
would drift independently). Here we group all flagged segments by their (tokenized)
source, ask the AI to choose ONE canonical target for the group, and emit a
per-segment decision (segmentguid -> Resolution) that fixes every member to that
canonical form. The engine applies these decisions as the single writer.
"""
from xml.sax.saxutils import escape as _xml_escape
from ..models import Resolution
from ..tags import detokenize
from .base import normalize_code

XSEG_CODES = {"3100", "3101"}

XSEG_SCHEMA = {
    "type": "object",
    "properties": {
        "canonical_target": {"type": "string"},
        "auto_apply": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string"},
    },
    "required": ["canonical_target", "auto_apply", "confidence", "rationale"],
    "additionalProperties": False,
}

_SYSTEM = """memoQ flagged several segments that share the SAME source but were translated
inconsistently (any language pair). Choose ONE canonical target form and return it, so every
occurrence becomes identical. Pick the variant that is most correct and complete (prefer the
form that best matches the source — e.g. keeps a trailing period or correct casing a brand name
requires); if all variants are wrong, return a corrected canonical form. Inline tags are shown as
markers like ⟦1:label⟧ — keep every marker exactly, never add or drop one. Set auto_apply=true only
when the canonical choice is unambiguous and safe; set auto_apply=false when a human should confirm
(genuine terminology/stylistic judgement, or you are not fully certain). Brand names, codes, and
dates that are correctly identical to the source are NOT inconsistencies — but if they are flagged
and DO differ, unify them to the source-faithful form."""


def _build_user(source, variants):
    lines = [f"SOURCE (shared by all occurrences):\n{source}\n",
             "CURRENT TARGET VARIANTS (each with how many segments use it):"]
    for tgt, count in variants:
        lines.append(f"- ({count}x) {tgt}")
    lines.append("\nReturn the single canonical target (keep all ⟦N:label⟧ markers).")
    return "\n".join(lines)


def _detok(canonical_tok, target_tags):
    """Detokenize the canonical form against a member's tag map. Returns
    (new_inner, ok). ok=False on marker mismatch (member needs manual review)."""
    try:
        if target_tags:
            return detokenize(_xml_escape(canonical_tok), target_tags), True
        return detokenize(canonical_tok, target_tags), True
    except ValueError:
        return None, False


def resolve_inconsistency_groups(issues, members_by_guid, ai_client) -> dict:
    """Group flagged members by source, pick a canonical target per group, and
    return {segmentguid: Resolution} for every member of a group that actually
    needs unifying (more than one distinct target). Groups already consistent are
    left out (the engine handles them / they re-QA clean)."""
    # segments carrying a 3100/3101 issue, de-duplicated, in first-seen order
    flagged, seen = [], set()
    for i in issues:
        if normalize_code(i.code) in XSEG_CODES and i.segmentguid not in seen:
            seen.add(i.segmentguid)
            flagged.append(i.segmentguid)

    groups = {}
    for guid in flagged:
        m = members_by_guid.get(guid)
        if m is not None:
            groups.setdefault(m.source_text, []).append(m)

    out = {}
    for source, members in groups.items():
        distinct = {m.target_text for m in members}
        if len(distinct) <= 1:
            continue  # already consistent — nothing to unify
        # variant -> count, most common first (gives the AI document-frequency signal)
        counts = {}
        for m in members:
            counts[m.target_text] = counts.get(m.target_text, 0) + 1
        variants = sorted(counts.items(), key=lambda kv: -kv[1])

        try:
            data = ai_client.resolve(_SYSTEM, _build_user(source, variants), XSEG_SCHEMA)
        except Exception as exc:
            for m in members:
                out[m.segmentguid] = Resolution(
                    action="fix", new_target=None, needs_approval=True, strategy="ai",
                    rationale=f"AI error choosing canonical form: {exc}")
            continue

        canonical = data.get("canonical_target", "")
        conf = {"high": 0.95, "medium": 0.6, "low": 0.3}.get(data.get("confidence"), 0.3)
        auto = data.get("auto_apply", False) and data.get("confidence") == "high"
        rationale = data.get("rationale", "")
        for m in members:
            new_inner, ok = _detok(canonical, m.target_tags)
            if not ok:
                out[m.segmentguid] = Resolution(
                    action="fix", new_target=None, confidence=conf, needs_approval=True,
                    strategy="ai",
                    rationale="Canonical form's tags don't match this segment; review manually. "
                              + rationale)
            else:
                out[m.segmentguid] = Resolution(
                    action="fix", new_target=new_inner, confidence=conf,
                    needs_approval=not auto, strategy="ai", rationale=rationale,
                    new_target_tokens=canonical)
    return out
