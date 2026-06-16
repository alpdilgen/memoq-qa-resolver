from ..models import Resolution
from ..casebuilder import build_cases
from ..context import build_case_payload
from ..ai import classify_case, build_system_prompt
from ..tags import detokenize

_CONF = {"high": 0.95, "medium": 0.6, "low": 0.3}


def resolve_inconsistencies(issues, members_by_guid, ai_client, glossary):
    """Batch-resolve 3100/3101 inconsistency issues. Returns {segmentguid: Resolution}."""
    members = list(members_by_guid.values())
    cases = build_cases(members)
    if not cases:
        return {}
    gloss_text = "\n".join(f"{k} = {v}" for k, v in (glossary or {}).items())
    system_prompt = build_system_prompt(gloss_text)

    out = {}
    for case in cases:
        payload = build_case_payload(case, members, glossary or {})
        try:
            decision = classify_case(ai_client, payload, system_prompt, model="")
        except Exception as exc:
            for m in case.members:
                out[m.segmentguid] = Resolution(
                    action="report", confidence=0.0, needs_approval=True,
                    strategy="ai", rationale=f"AI error: {exc}")
            continue
        conf = _CONF.get(decision.confidence, 0.3)
        needs = decision.confidence != "high"
        if decision.category == "false_positive":
            for m in case.members:
                out[m.segmentguid] = Resolution(
                    action="ignore", confidence=conf, needs_approval=needs,
                    strategy="ai", rationale=decision.rationale)
        elif decision.category == "pick_best" and decision.chosen_member_id:
            chosen = next((m for m in case.members if m.tu_id == decision.chosen_member_id), None)
            if chosen is None:
                continue
            new_inner = detokenize(chosen.target_text, chosen.target_tags)
            for m in case.members:
                out[m.segmentguid] = Resolution(
                    action="fix", new_target=new_inner, confidence=conf,
                    needs_approval=needs, strategy="ai", rationale=decision.rationale)
        elif decision.category == "differentiate":
            wanted = {d["source_key"]: d["new_target"] for d in decision.differentiated}
            for m in case.members:
                if m.source_text in wanted:
                    from xml.sax.saxutils import escape as _esc
                    try:
                        new_inner = detokenize(_esc(wanted[m.source_text]), m.target_tags)
                    except ValueError:
                        out[m.segmentguid] = Resolution(
                            action="report", confidence=0.0, needs_approval=True,
                            strategy="ai", rationale="AI target dropped a tag marker.")
                        continue
                    out[m.segmentguid] = Resolution(
                        action="fix", new_target=new_inner, confidence=conf,
                        needs_approval=needs, strategy="ai", rationale=decision.rationale)
    return out
