"""Batched per-segment AI resolution: one LLM call resolves K independent segments,
cutting hundreds of sequential calls down to a handful. Each returned segment is run
through the SAME guards as the single-segment resolver (resolution_from_ai_data), and
any segment the model omits — or the whole batch on an API error — falls back to
needs_approval so nothing is ever silently dropped (conservation)."""
from .ai_segment_resolver import resolution_from_ai_data, _SYSTEM, SEGMENT_SCHEMA
from .base import normalize_code
from ..models import Resolution
from ..qa_codes import describe_code
from ..whitespace import align_whitespace, collapse_internal_spaces

_BATCH_SYSTEM = _SYSTEM + """

You are given SEVERAL segments at once. Return a JSON object with a "segments" array
containing ONE entry per input segment, each tagged with its segment_id exactly as given.
Apply the rules above independently to each segment."""

# Same per-segment fields as SEGMENT_SCHEMA, wrapped in an array keyed by segment_id.
_ITEM_PROPS = dict(SEGMENT_SCHEMA["properties"])
_ITEM_PROPS["segment_id"] = {"type": "string"}
BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _ITEM_PROPS,
                "required": ["segment_id", "code_verdicts", "fixed_target", "confidence", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["segments"],
    "additionalProperties": False,
}


def _build_batch_user(items):
    lines = ["Resolve EACH of the following segments independently. Return one entry per "
             "segment_id in the \"segments\" array.\n"]
    for key, member, issues in items:
        lines.append(f"=== SEGMENT {key} ===")
        lines.append("FLAGGED CODES:")
        for i in issues:
            lines.append(f"- code {i.code}: {describe_code(normalize_code(i.code), i.problemname)}"
                         + (f"  [details: {i.args}]" if i.args else ""))
        candidate = collapse_internal_spaces(align_whitespace(member.source_text, member.target_text))
        lines.append(f"SOURCE: {member.source_text}")
        lines.append(f"CURRENT TARGET: {member.target_text}")
        if candidate != member.target_text:
            lines.append(f"WHITESPACE-NORMALIZED CANDIDATE: {candidate}")
        lines.append("")
    lines.append("Keep every ⟦id:label⟧ marker exactly; a verdict per code; honest integer confidence.")
    return "\n".join(lines)


def _fallback(rationale):
    return Resolution(action="fix", new_target=None, confidence=0.0,
                      needs_approval=True, strategy="ai", rationale=rationale)


def resolve_segment_batch(items, ai_client, threshold=100) -> dict:
    """items: list of (key, member, issues). Returns {key: Resolution}. One AI call
    for the whole batch; omitted segments and API errors -> needs_approval fallback."""
    if not items:
        return {}
    try:
        data = ai_client.resolve(_BATCH_SYSTEM, _build_batch_user(items), BATCH_SCHEMA)
    except Exception as exc:
        return {key: _fallback(f"AI batch error: {exc}") for key, _, _ in items}

    by_id = {}
    for entry in data.get("segments", []):
        sid = str(entry.get("segment_id", ""))
        if sid:
            by_id[sid] = entry

    out = {}
    for key, member, issues in items:
        entry = by_id.get(str(key))
        if entry is None:
            out[key] = _fallback("AI omitted this segment in the batch; review manually.")
        else:
            out[key] = resolution_from_ai_data(member, issues, entry, threshold)
    return out
