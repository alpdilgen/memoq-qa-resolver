from xml.sax.saxutils import escape as _xml_escape
from ..models import Resolution
from ..tags import detokenize
from ..taginv import count_parity
from ..qa_codes import describe_code
from ..whitespace import align_whitespace, collapse_internal_spaces
from .base import normalize_code

SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "code_verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["fix", "false_positive"]},
                },
                "required": ["code", "verdict"],
                "additionalProperties": False,
            },
        },
        "fixed_target": {"type": "string"},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
    },
    "required": ["code_verdicts", "fixed_target", "confidence", "rationale"],
    "additionalProperties": False,
}

_SYSTEM = """You resolve one translation segment that memoQ QA flagged (any language pair).
Inline tags appear as markers ⟦id:label⟧ (e.g. ⟦1:<cf size=9.5>⟧). KEEP EVERY marker exactly as
given — the same set and the same count. Do NOT add, remove, reorder, or alter any tag; tag-structure
problems are handled separately. You may only change the TEXT and whitespace to resolve the flagged codes.

For EACH flagged code decide a verdict:
- "false_positive": the current target is already correct and the flag is a mechanical artifact —
  e.g. the flagged sign is inside an entity like &quot; or &amp;, the text is a brand/code/date
  correctly identical to the source, or the source contains the very same pattern. Do not change it.
- "fix": a genuine error; correct it per the code's official meaning.

Return fixed_target = the corrected target with every marker preserved. If every code is a
false_positive, return the current target unchanged. Give an HONEST integer confidence 0-100; use
100 ONLY when you are certain the fix is correct and safe. Below the auto-apply threshold a human confirms."""


def _build_user(member, issues):
    lines = ["FLAGGED CODES on this segment:"]
    for i in issues:
        lines.append(f"- code {i.code}: {describe_code(normalize_code(i.code), i.problemname)}"
                     + (f"  [details: {i.args}]" if i.args else ""))
    candidate = collapse_internal_spaces(align_whitespace(member.source_text, member.target_text))
    lines.append(f"\nSOURCE: {member.source_text}")
    lines.append(f"CURRENT TARGET: {member.target_text}")
    if candidate != member.target_text:
        lines.append(f"WHITESPACE-NORMALIZED CANDIDATE (start from this; whitespace already aligned): {candidate}")
    lines.append("\nReturn fixed_target keeping every ⟦id:label⟧ marker exactly, a verdict per code, "
                 "and an honest integer confidence.")
    return "\n".join(lines)


def resolve_segment(member, issues, context, ai_client, threshold=100) -> Resolution:
    user = _build_user(member, issues)
    try:
        data = ai_client.resolve(_SYSTEM, user, SEGMENT_SCHEMA)
    except Exception as exc:
        return Resolution(action="report", confidence=0.0, needs_approval=True,
                          strategy="ai", rationale=f"AI error: {exc}")

    verdicts = {normalize_code(v.get("code", "")): v.get("verdict", "fix")
                for v in data.get("code_verdicts", [])}
    conf_int = int(data.get("confidence", 0))
    conf = conf_int / 100.0
    rationale = data.get("rationale", "")
    seg_codes = [normalize_code(i.code) for i in issues]
    fp_codes = [c for c in seg_codes if verdicts.get(c) == "false_positive"]
    fix_codes = [c for c in seg_codes if verdicts.get(c, "fix") != "false_positive"]

    # Every code a false positive -> ignore; translation untouched.
    if not fix_codes:
        return Resolution(action="ignore", new_target=None, confidence=conf,
                          needs_approval=conf_int < threshold, strategy="ai",
                          rationale=rationale, ignore_codes=fp_codes)

    fixed_tok = data.get("fixed_target", "")
    # Cardinal guard: the AI must preserve the target's tags exactly (it may only
    # change text/whitespace). Any tag change -> cannot auto-apply, human reviews.
    if not count_parity(fixed_tok, member.target_text):
        return Resolution(action="fix", new_target=None, confidence=conf, needs_approval=True,
                          strategy="ai", ignore_codes=fp_codes,
                          rationale="AI altered the segment's tags; review manually. " + rationale)
    try:
        new_inner = (detokenize(_xml_escape(fixed_tok), member.target_tags)
                     if member.target_tags else detokenize(fixed_tok, member.target_tags))
    except ValueError:
        return Resolution(action="fix", new_target=None, confidence=conf, needs_approval=True,
                          strategy="ai", ignore_codes=fp_codes,
                          rationale="AI changed the tag markers; review manually. " + rationale)
    return Resolution(action="fix", new_target=new_inner, confidence=conf,
                      needs_approval=conf_int < threshold, strategy="ai",
                      rationale=rationale, ignore_codes=fp_codes,
                      new_target_tokens=fixed_tok)
