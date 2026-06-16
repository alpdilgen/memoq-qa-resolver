from .models import ReviewSession, ResolvedItem
from .parser import parse_issues, parse_languages
from .registry import STRATEGY_BY_CODE, register_resolver, get_resolver
from .resolvers.base import normalize_code, ReportOnlyResolver
from .resolvers.whitespace_resolver import WhitespaceResolver
from .resolvers.inconsistency_resolver import resolve_inconsistencies
from .apply import apply_resolved_items

# Register deterministic resolvers for their codes (one shared instance).
_WS = WhitespaceResolver()
for _code, _strat in STRATEGY_BY_CODE.items():
    if _strat == "deterministic":
        register_resolver(_code, _WS)

_INCONSISTENCY_CODES = {"3100", "3101"}


def analyze(content: bytes, ai_client=None, glossary=None) -> ReviewSession:
    src_lang, tgt_lang = parse_languages(content)
    issues, members = parse_issues(content)

    # Batch AI inconsistency resolution (cross-segment).
    inconsistency_res = {}
    if ai_client is not None and any(normalize_code(i.code) in _INCONSISTENCY_CODES for i in issues):
        inconsistency_res = resolve_inconsistencies(
            [i for i in issues if normalize_code(i.code) in _INCONSISTENCY_CODES],
            members, ai_client, glossary or {})

    auto, pending, report = [], [], []
    for idx, issue in enumerate(issues):
        member = members.get(issue.segmentguid)
        code = normalize_code(issue.code)
        if member is None:
            continue
        if code in _INCONSISTENCY_CODES:
            res = inconsistency_res.get(issue.segmentguid)
            if res is None:
                res = ReportOnlyResolver().resolve(issue, member, None)
        else:
            res = get_resolver(issue).resolve(issue, member, None)

        item = ResolvedItem(
            item_id=f"{issue.segmentguid}:{code}:{idx}",
            segmentguid=issue.segmentguid, tu_id=issue.tu_id,
            code=code, problemname=issue.problemname,
            source_preview=member.source_text,
            current_target_preview=member.target_text,
            proposed_target_preview=res.new_target,
            resolution=res,
        )
        if res.action == "report":
            report.append(item)
        elif res.needs_approval:
            pending.append(item)
        else:
            auto.append(item)

    return ReviewSession(src_lang, tgt_lang, auto, pending, report)


def apply(content: bytes, items) -> bytes:
    """Apply the given ResolvedItems (typically auto_applied + approved pending)
    and return corrected mqxliff bytes."""
    return apply_resolved_items(content, items)
