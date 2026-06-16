from dataclasses import replace
from .models import ReviewSession, ResolvedItem, Resolution
from .parser import parse_issues, parse_languages
from .registry import STRATEGY_BY_CODE, register_resolver, get_resolver
from .resolvers.base import normalize_code, ReportOnlyResolver
from .resolvers.whitespace_resolver import WhitespaceResolver
from .resolvers.inconsistency_resolver import resolve_inconsistencies
from .resolvers.inconsistency_xseg import resolve_inconsistency_groups
from .resolvers.ai_segment_resolver import resolve_segment
from .qa_codes import BULK_SUITABLE_CODES, RISKY_CODES, describe_code
from .apply import apply_resolved_items
from .tags import detokenize

# Register deterministic resolvers for their codes (one shared instance).
_WS = WhitespaceResolver()
for _code, _strat in STRATEGY_BY_CODE.items():
    if _strat == "deterministic":
        register_resolver(_code, _WS)


def _disp(text, tags):
    """Return the detokenized (human-readable) form of a tokenized segment text.
    Falls back to the tokenized form only if detokenize raises, so the UI never
    shows raw internal marker characters to the user."""
    try:
        return detokenize(text, tags)
    except ValueError:
        return text


def reconcile(session) -> None:
    """Ledger invariant: every detected issue lands in exactly one bucket.
    Asserts fix + ignore + needs_approval == total_issues. A mismatch means an
    issue was silently dropped (a bug)."""
    accounted = sum(it.issue_count for it in session.auto_applied)
    accounted += sum(it.issue_count for it in session.pending)
    if accounted != session.total_issues:
        raise AssertionError(
            f"ledger mismatch: accounted {accounted} != detected {session.total_issues}")


def analyze(content: bytes, ai_client=None, glossary=None) -> ReviewSession:
    src_lang, tgt_lang = parse_languages(content)
    issues, members = parse_issues(content)
    total_issues = len(issues)

    # group issues by segment, preserve segment order (by numeric tu_id)
    by_seg = {}
    for it in issues:
        by_seg.setdefault(it.segmentguid, []).append(it)
    ordered_guids = sorted(by_seg, key=lambda g: int(by_seg[g][0].tu_id)
                           if by_seg[g][0].tu_id.isdigit() else 0)

    # Phase A: cross-segment inconsistency (3100/3101). Unify each group of
    # identical-source segments to one AI-chosen canonical target BEFORE the
    # per-segment pass, so the per-segment pass is the single writer.
    xseg = {}
    if ai_client is not None:
        xseg = resolve_inconsistency_groups(issues, members, ai_client)

    auto, pending = [], []
    for guid in ordered_guids:
        seg_issues = by_seg[guid]
        n_issues = len(seg_issues)
        primary = seg_issues[0]
        member = members.get(guid)
        if member is None:
            # pathological: a flagged segment we couldn't parse. Never drop it;
            # surface as needs_approval so it stays in the ledger.
            res = Resolution(action="fix", new_target=None, needs_approval=True,
                             strategy="ai", rationale="segment not found; handle manually.")
            pending.append(ResolvedItem(
                item_id=f"{guid}:{primary.code}", segmentguid=guid, tu_id=primary.tu_id,
                code=primary.code, problemname=primary.problemname,
                source_preview="", current_target_preview="", proposed_target_preview=None,
                resolution=res, issue_count=n_issues))
            continue
        codes = [normalize_code(i.code) for i in seg_issues]
        all_bulk = all(c in BULK_SUITABLE_CODES for c in codes)

        if guid in xseg:
            # Phase A already decided this segment's target (cross-segment unification).
            res = xseg[guid]
        elif all_bulk:
            res = _WS.resolve(seg_issues[0], member, None)
        elif ai_client is not None:
            res = resolve_segment(member, seg_issues, None, ai_client)
        else:
            # no AI available -> surface as a suggestion needing manual handling,
            # never silently dropped, never auto-applied
            res = Resolution(action="fix", new_target=None, confidence=0.0,
                             needs_approval=True, strategy="ai",
                             rationale="AI is required to resolve "
                                       + ", ".join(sorted(set(codes)))
                                       + "; enable AI or fix manually.")

        # Deterministic no-op (whitespace already aligned / nothing to change):
        # this is a false positive -> IGNORE (accounted), never silently skipped.
        if (res.new_target is None and res.strategy == "deterministic"
                and res.action in ("fix", "report")):
            res = Resolution(action="ignore", new_target=None, needs_approval=False,
                             strategy="deterministic",
                             rationale="flagged but target already correct (false positive)")

        # Risky tag-structure codes must never auto-apply; force approval.
        if any(c in RISKY_CODES for c in codes):
            res = replace(res, needs_approval=True)

        src_disp = _disp(member.source_text, member.source_tags)
        cur_disp = _disp(member.target_text, member.target_tags)
        prop_disp = res.new_target if res.new_target is not None else cur_disp
        item = ResolvedItem(
            item_id=f"{guid}:{primary.code}",
            segmentguid=guid, tu_id=primary.tu_id,
            code=primary.code, problemname=primary.problemname,
            source_preview=src_disp,
            current_target_preview=cur_disp,
            proposed_target_preview=prop_disp,
            resolution=res,
            issue_count=n_issues,
        )
        if res.needs_approval:
            pending.append(item)
        else:
            auto.append(item)

    session = ReviewSession(src_lang, tgt_lang, auto, pending,
                            report_only=[], total_issues=total_issues)
    reconcile(session)
    return session


def apply(content: bytes, items) -> bytes:
    """Apply the given ResolvedItems (typically auto_applied + approved pending)
    and return corrected mqxliff bytes."""
    return apply_resolved_items(content, items)


def session_to_view(session) -> dict:
    """Serializable view-model of a ReviewSession for any front-end."""
    def rows(bucket):
        out = []
        for it in bucket:
            r = it.resolution
            out.append({
                "item_id": it.item_id, "code": it.code, "tu_id": it.tu_id,
                "problemname": it.problemname, "source": it.source_preview,
                "current_target": it.current_target_preview,
                "proposed_target": it.proposed_target_preview,
                "action": r.action, "confidence": r.confidence,
                "needs_approval": r.needs_approval, "strategy": r.strategy,
                "rationale": r.rationale,
            })
        return out
    return {
        "source_lang": session.source_lang, "target_lang": session.target_lang,
        "auto_applied": rows(session.auto_applied),
        "pending": rows(session.pending),
        "report_only": rows(session.report_only),
    }


def items_for_apply(session, approved_ids, edits=None):
    """Return the ResolvedItems to apply: all auto_applied + approved pending.
    For an approved pending item with an edit, force action='fix' with the
    edited target text (written verbatim; engine.apply validates the XML)."""
    edits = edits or {}
    out = list(session.auto_applied)
    approved_ids = set(approved_ids or ())
    for it in session.pending:
        if it.item_id not in approved_ids:
            continue
        edited = edits.get(it.item_id)
        if edited is not None and edited != (it.resolution.new_target or ""):
            new_res = replace(it.resolution, action="fix", new_target=edited)
            out.append(replace(it, resolution=new_res))
        else:
            out.append(it)
    return out
