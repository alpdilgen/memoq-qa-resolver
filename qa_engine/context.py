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
