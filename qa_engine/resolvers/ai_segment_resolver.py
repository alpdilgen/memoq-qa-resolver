import json
from xml.sax.saxutils import escape as _xml_escape
from ..models import Resolution
from ..tags import detokenize, markers_in
from ..qa_codes import describe_code

SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "fixed_target": {"type": "string"},
        "auto_apply": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string"},
    },
    "required": ["fixed_target", "auto_apply", "confidence", "rationale"],
    "additionalProperties": False,
}

_SYSTEM = """You fix one translation segment that memoQ's QA flagged (any language pair).
Inline tags are shown as markers like ⟦1⟧ — keep every marker exactly, never add or drop one.
You are given the QA issue(s) with their official meaning, the source, the current target, and
the localization args memoQ provided. Return the corrected target. Set auto_apply=true ONLY when
the fix is unambiguous and safe (e.g. a clear mechanical or factual correction); set auto_apply=false
when a human should confirm (anything requiring stylistic/semantic judgment, terminology choices,
restructuring, or where you are not fully certain). If the current target is already correct for the
flagged issue, return it unchanged with auto_apply=true and say so in the rationale."""


def _build_user(member, issues):
    lines = ["ISSUES on this segment:"]
    for i in issues:
        lines.append(f"- code {i.code}: {describe_code(i.code, i.problemname)}"
                     + (f"  [details: {i.args}]" if i.args else ""))
    lines.append(f"\nSOURCE: {member.source_text}")
    lines.append(f"CURRENT TARGET: {member.target_text}")
    lines.append("\nReturn the corrected target (keep all ⟦N⟧ markers).")
    return "\n".join(lines)


def resolve_segment(member, issues, context, ai_client) -> Resolution:
    user = _build_user(member, issues)
    try:
        data = ai_client.resolve(_SYSTEM, user, SEGMENT_SCHEMA)
    except Exception as exc:
        return Resolution(action="report", confidence=0.0, needs_approval=True,
                          strategy="ai", rationale=f"AI error: {exc}")
    fixed_tok = data["fixed_target"]
    conf = {"high": 0.95, "medium": 0.6, "low": 0.3}.get(data.get("confidence"), 0.3)
    # detokenize defensively: markers must match the segment's tag map
    try:
        new_inner = detokenize(_xml_escape(fixed_tok), member.target_tags) \
            if member.target_tags else detokenize(fixed_tok, member.target_tags)
        bad_markers = False
    except ValueError:
        bad_markers = True
    if bad_markers:
        return Resolution(action="fix", new_target=None, confidence=conf,
                          needs_approval=True, strategy="ai",
                          rationale="AI changed the tag markers; please review/fix manually. "
                                    + data.get("rationale", ""))
    needs = (not data.get("auto_apply", False))
    return Resolution(action="fix", new_target=new_inner, confidence=conf,
                      needs_approval=needs, strategy="ai", rationale=data.get("rationale", ""))
