from dataclasses import replace
from .models import ReviewSession, ResolvedItem, Resolution, Progress
from .parser import parse_issues, parse_languages
from .registry import STRATEGY_BY_CODE, register_resolver, get_resolver
from .resolvers.base import normalize_code, ReportOnlyResolver
from .resolvers.whitespace_resolver import WhitespaceResolver
from .resolvers.inconsistency_resolver import resolve_inconsistencies
from .resolvers.inconsistency_xseg import resolve_inconsistency_groups
from .resolvers.ai_segment_resolver import resolve_segment
from .qa_codes import BULK_SUITABLE_CODES, RISKY_CODES, describe_code
from .tagfix import plan_tag_structure, TAG_STRUCTURE_CODES
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


def _plan_segment(guid, member, seg_issues, ai_client, xseg, threshold) -> Resolution:
    """Single combined resolution for one segment, covering ALL its codes:
    deterministic whitespace + deterministic tag-structure (2016 false-positive,
    2011 count-parity) + LLM for content codes; per-code false positives recorded
    in ignore_codes. Auto-applies only when nothing needs human judgement."""
    codes = [normalize_code(i.code) for i in seg_issues]
    ws_codes = [c for c in codes if c in BULK_SUITABLE_CODES]
    tag_codes = [c for c in codes if c in TAG_STRUCTURE_CODES]
    content_codes = [c for c in codes
                     if c not in BULK_SUITABLE_CODES and c not in TAG_STRUCTURE_CODES]

    tag_ignore, additions, remaining_tag = ([], [], [])
    if tag_codes:
        tag_ignore, additions, remaining_tag = plan_tag_structure(member, tag_codes)

    base_inner = None
    ignore_content = []
    need = False
    conf = 1.0
    strategy = "deterministic"
    rationale = ""

    if guid in xseg:                                   # cross-segment inconsistency decision
        r = xseg[guid]
        base_inner, need, conf, rationale = r.new_target, r.needs_approval, r.confidence, r.rationale
        ignore_content = list(r.ignore_codes or [])
        strategy = "ai"
    elif content_codes:
        if ai_client is not None:
            r = resolve_segment(member, seg_issues, None, ai_client, threshold)
            base_inner, need, conf, rationale = r.new_target, r.needs_approval, r.confidence, r.rationale
            ignore_content = list(r.ignore_codes or [])
            strategy = "ai"
        else:
            need, strategy = True, "ai"
            rationale = "AI required to resolve " + ", ".join(sorted(set(content_codes)))
    elif ws_codes:                                     # whitespace-only (no content)
        wr = _WS.resolve(seg_issues[0], member, None)
        if wr.new_target is None:                      # already correct -> false positive
            ignore_content = list(dict.fromkeys(ws_codes))
            rationale = "whitespace already correct (false positive)"
        else:
            base_inner, rationale = wr.new_target, wr.rationale

    # 2011: append the missing self-contained tags to reach count parity.
    if additions:
        if base_inner is None:
            try:
                base_inner = detokenize(member.target_text, member.target_tags)
            except ValueError:
                base_inner, need = None, True
        if base_inner is not None:
            base_inner = base_inner + "".join(additions)

    ignore_codes = list(dict.fromkeys(list(ignore_content) + list(tag_ignore)))
    if remaining_tag:                                  # 2010/2015/unsafe 2011 -> human
        need = True
    if base_inner is None and not ignore_codes:        # genuine no-op -> never auto
        need = True

    action = "ignore" if (base_inner is None and ignore_codes) else "fix"
    return Resolution(action=action, new_target=base_inner, confidence=conf,
                      needs_approval=need, strategy=strategy, rationale=rationale,
                      ignore_codes=ignore_codes)


def reconcile(session) -> None:
    """Ledger invariant: every detected issue lands in exactly one bucket.
    Asserts fix + ignore + needs_approval == total_issues. A mismatch means an
    issue was silently dropped (a bug)."""
    accounted = sum(it.issue_count for it in session.auto_applied)
    accounted += sum(it.issue_count for it in session.pending)
    if accounted != session.total_issues:
        raise AssertionError(
            f"ledger mismatch: accounted {accounted} != detected {session.total_issues}")


def _verdict_label(res) -> str:
    if res.needs_approval:
        return "needs_approval"
    return res.action          # "fix" | "ignore"


def analyze_stream(content: bytes, ai_client=None, glossary=None, threshold=100):
    """Generator: process each flagged segment in order, yielding a Progress after
    each one (for a live UI). Returns the finished ReviewSession (PEP 380 — caught
    via StopIteration.value, or simply use analyze())."""
    src_lang, tgt_lang = parse_languages(content)
    issues, members = parse_issues(content)
    total_issues = len(issues)

    by_seg = {}
    for it in issues:
        by_seg.setdefault(it.segmentguid, []).append(it)
    ordered_guids = sorted(by_seg, key=lambda g: int(by_seg[g][0].tu_id)
                           if by_seg[g][0].tu_id.isdigit() else 0)
    total_segs = len(ordered_guids)

    # Phase A: cross-segment inconsistency (3100/3101) decided before the per-segment pass.
    xseg = {}
    if ai_client is not None:
        xseg = resolve_inconsistency_groups(issues, members, ai_client)

    auto, pending = [], []
    for idx, guid in enumerate(ordered_guids, 1):
        seg_issues = by_seg[guid]
        n_issues = len(seg_issues)
        primary = seg_issues[0]
        seg_codes = [normalize_code(i.code) for i in seg_issues]
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
            yield Progress(idx, total_segs, primary.tu_id, seg_codes,
                           primary.problemname, "needs_approval")
            continue
        res = _plan_segment(guid, member, seg_issues, ai_client, xseg, threshold)

        src_disp = _disp(member.source_text, member.source_tags)
        cur_disp = _disp(member.target_text, member.target_tags)
        prop_disp = res.new_target if res.new_target is not None else cur_disp
        # Token-form proposal seeds the edit box and round-trips by id on apply;
        # fall back to the current target's tokens when there's no rewrite.
        prop_tokens = res.new_target_tokens if res.new_target_tokens is not None else member.target_text
        item = ResolvedItem(
            item_id=f"{guid}:{primary.code}",
            segmentguid=guid, tu_id=primary.tu_id,
            code=primary.code, problemname=primary.problemname,
            source_preview=src_disp,
            current_target_preview=cur_disp,
            proposed_target_preview=prop_disp,
            resolution=res,
            issue_count=n_issues,
            tags=dict(member.target_tags),
            proposed_tokens=prop_tokens,
        )
        (pending if res.needs_approval else auto).append(item)
        yield Progress(idx, total_segs, primary.tu_id, seg_codes,
                       primary.problemname, _verdict_label(res))

    session = ReviewSession(src_lang, tgt_lang, auto, pending,
                            report_only=[], total_issues=total_issues)
    reconcile(session)
    return session


def analyze(content: bytes, ai_client=None, glossary=None, threshold=100) -> ReviewSession:
    """Run the full analysis (no progress callbacks). Built on analyze_stream."""
    gen = analyze_stream(content, ai_client, glossary, threshold)
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


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

    Approved pending items carry an edit in ⟦id:label⟧ token form. If the user
    left it unchanged, apply the precomputed resolution. If they edited it,
    detokenize their tokens back to XML by id (tags preserved by id even if the
    user mistypes a label); on a broken token set we keep the original so the
    file is never corrupted (apply also guards against any stray markers)."""
    from xml.sax.saxutils import escape as _xml_escape
    edits = edits or {}
    out = list(session.auto_applied)
    approved_ids = set(approved_ids or ())
    for it in session.pending:
        if it.item_id not in approved_ids:
            continue
        edited = edits.get(it.item_id)
        if edited is None or edited == it.proposed_tokens:
            out.append(it)
            continue
        try:
            new_inner = (detokenize(_xml_escape(edited), it.tags)
                         if it.tags else detokenize(edited, it.tags))
        except ValueError:
            out.append(it)   # broken tokens -> keep the safe original
            continue
        new_res = replace(it.resolution, action="fix", new_target=new_inner)
        out.append(replace(it, resolution=new_res))
    return out
