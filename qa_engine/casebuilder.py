import difflib
from .models import Case


def _has_inconsistency(member) -> bool:
    return any(pn == "inconsistent translation" for pn, _ in member.warning_keys)


def build_cases(members: list) -> list:
    warned = [m for m in members if _has_inconsistency(m)]

    # target-inconsistency: group warned members by identical (tokenized) target
    by_target = {}
    for m in warned:
        by_target.setdefault(m.target_text, []).append(m)
    # source-inconsistency: group warned members by identical (tokenized) source
    by_source = {}
    for m in warned:
        by_source.setdefault(m.source_text, []).append(m)

    cases = []
    seen_ids = set()
    cid = 0

    # source-inconsistency first: a source mapping to >1 distinct target
    for src, group in by_source.items():
        targets = {m.target_text for m in group}
        # pull in non-warned members that share this source (the "other" variant)
        same_source = [m for m in members if m.source_text == src]
        all_targets = {m.target_text for m in same_source}
        if len(all_targets) > 1:
            cid += 1
            cases.append(Case(
                id=f"S{cid}", type="source_inconsistency",
                members=same_source,
                mechanical_diff=describe_diff(sorted(all_targets)),
            ))
            seen_ids.update(m.tu_id for m in same_source)

    # target-inconsistency: a target mapping to >1 distinct source
    for tgt, group in by_target.items():
        if any(m.tu_id in seen_ids for m in group):
            continue
        same_target = [m for m in members if m.target_text == tgt]
        all_sources = {m.source_text for m in same_target}
        if len(all_sources) > 1:
            cid += 1
            cases.append(Case(
                id=f"T{cid}", type="target_inconsistency",
                members=same_target,
                mechanical_diff=describe_diff(sorted(all_sources)),
            ))
            seen_ids.update(m.tu_id for m in same_target)

    return cases


def describe_diff(strings: list) -> str:
    """Plain-English mechanical difference between variant strings."""
    if len(strings) < 2:
        return "single variant"
    a, b = strings[0], strings[1]
    if a.strip() == b.strip() and a != b:
        return "differ only by leading/trailing whitespace"
    if a.replace(" ", "") == b.replace(" ", "") and a != b:
        return "differ only by internal whitespace"
    if a.lower() == b.lower():
        return "differ only by letter case"
    sm = difflib.SequenceMatcher(None, a, b)
    if sm.ratio() > 0.93:
        return f"differ by a few characters (likely a typo): {a!r} vs {b!r}"
    return f"meaningfully different: {a!r} vs {b!r}"
