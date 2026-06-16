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
    user_content = "Resolve this inconsistency case:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    data = client.resolve(system_prompt, user_content, DECISION_SCHEMA)

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
