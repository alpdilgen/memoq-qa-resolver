from dataclasses import replace
from .models import ReviewSession, ResolvedItem, Resolution, Progress
from .parser import parse_issues, parse_languages
from .registry import STRATEGY_BY_CODE, register_resolver, get_resolver
from .resolvers.base import normalize_code, ReportOnlyResolver
from .resolvers.whitespace_resolver import WhitespaceResolver
from .resolvers.inconsistency_resolver import resolve_inconsistencies
from .resolvers.inconsistency_xseg import resolve_inconsistency_groups
from .resolvers.ai_segment_resolver import resolve_segment
from .resolvers.batch_resolver import resolve_segment_batch
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


def _needs_ai_segment(guid, seg_codes, xseg, ignore_all=()) -> bool:
    """True if this segment requires an AI call (content codes, or whitespace on a
    reordered segment) and isn't already decided by Phase A. Codes the user bulk-
    ignored don't count."""
    if guid in xseg:
        return False
    active = [c for c in seg_codes if c not in ignore_all]
    ws = [c for c in active if c in BULK_SUITABLE_CODES]
    content = [c for c in active
               if c not in BULK_SUITABLE_CODES and c not in TAG_STRUCTURE_CODES]
    return bool(content or (ws and "2016" in active))


def _plan_segment(guid, member, seg_issues, ai_client, xseg, threshold,
                  ai_result=None, ignore_all=()) -> Resolution:
    """Single combined resolution for one segment, covering ALL its codes:
    deterministic whitespace + deterministic tag-structure (2016 false-positive,
    2011 count-parity) + LLM for content codes; per-code false positives recorded
    in ignore_codes. Codes in `ignore_all` are bulk-marked false-positive (translation
    untouched) and skip all processing. Auto-applies only when nothing needs human judgement."""
    all_codes = [normalize_code(i.code) for i in seg_issues]
    forced_ignore = [c for c in all_codes if c in ignore_all]
    codes = [c for c in all_codes if c not in ignore_all]   # codes still to process
    ws_codes = [c for c in codes if c in BULK_SUITABLE_CODES]
    tag_codes = [c for c in codes if c in TAG_STRUCTURE_CODES]
    content_codes = [c for c in codes
                     if c not in BULK_SUITABLE_CODES and c not in TAG_STRUCTURE_CODES]
    # 2016 means the target reordered the tags — positional whitespace alignment is
    # then unreliable, so any whitespace on a reordered segment goes to the AI
    # (which sees source+target and is tag-guarded) rather than the deterministic aligner.
    reordered = "2016" in codes

    tag_ignore, tag_target, remaining_tag = ([], None, [])
    if tag_codes:
        tag_ignore, tag_target, remaining_tag = plan_tag_structure(member, tag_codes)

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
    elif content_codes or (ws_codes and reordered):
        # AI handles content codes and/or whitespace on a reordered segment. Use a
        # precomputed batch result when provided, else a single per-segment call.
        r = ai_result
        if r is None and ai_client is not None:
            r = resolve_segment(member, seg_issues, None, ai_client, threshold)
        if r is not None:
            base_inner, need, conf, rationale = r.new_target, r.needs_approval, r.confidence, r.rationale
            ignore_content = list(r.ignore_codes or [])
            strategy = "ai"
        else:
            need, strategy = True, "ai"
            rationale = ("AI required to resolve "
                         + ", ".join(sorted(set(content_codes) | (set(ws_codes) if reordered else set()))))
    elif ws_codes:                                     # whitespace-only, not reordered -> deterministic
        wr = _WS.resolve(seg_issues[0], member, None)
        if wr.new_target is None:                      # already correct -> false positive
            ignore_content = list(dict.fromkeys(ws_codes))
            rationale = "whitespace already correct (false positive)"
        else:
            base_inner, rationale = wr.new_target, wr.rationale

    # 2011: a deterministic tag-structure rewrite (missing tags inserted in source
    # order) supersedes the text-only base when one was built.
    if tag_target is not None:
        base_inner = tag_target

    ignore_codes = list(dict.fromkeys(list(ignore_content) + list(tag_ignore) + list(forced_ignore)))
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


def _make_item(guid, member, seg_issues, res) -> ResolvedItem:
    primary = seg_issues[0]
    src_disp = _disp(member.source_text, member.source_tags)
    cur_disp = _disp(member.target_text, member.target_tags)
    prop_disp = res.new_target if res.new_target is not None else cur_disp
    # Token-form proposal seeds the edit box and round-trips by id on apply.
    prop_tokens = res.new_target_tokens if res.new_target_tokens is not None else member.target_text
    return ResolvedItem(
        item_id=f"{guid}:{primary.code}", segmentguid=guid, tu_id=primary.tu_id,
        code=primary.code, problemname=primary.problemname,
        source_preview=src_disp, current_target_preview=cur_disp,
        proposed_target_preview=prop_disp, resolution=res, issue_count=len(seg_issues),
        tags=dict(member.target_tags), proposed_tokens=prop_tokens,
    )


def analyze_stream(content: bytes, ai_client=None, glossary=None, threshold=100,
                   batch_size=1, checkpoint=None, ignore_all_codes=None):
    """Generator: resolve each flagged segment, yielding a Progress as each finalizes.
    Returns the finished ReviewSession (PEP 380 — via StopIteration.value, or use analyze()).

    batch_size>1 sends content/AI segments to the LLM in groups of that size (far fewer
    calls on big files). A `checkpoint` (qa_engine.checkpoint.Checkpoint) caches each
    segment's result and is flushed after every batch, so an interrupted run resumes
    instead of restarting — and partial work is never lost."""
    src_lang, tgt_lang = parse_languages(content)
    issues, members = parse_issues(content)
    total_issues = len(issues)
    ignore_all = {normalize_code(c) for c in (ignore_all_codes or ())}

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
    done = [0]

    def _emit(guid, item):
        (pending if item.resolution.needs_approval else auto).append(item)
        if checkpoint is not None:
            checkpoint.save_item(item)
        done[0] += 1
        codes = [normalize_code(i.code) for i in by_seg[guid]]
        return Progress(done[0], total_segs, item.tu_id, codes,
                        item.problemname, _verdict_label(item.resolution))

    ai_queue = []   # [(guid, member, seg_issues)] awaiting a batched AI call

    def _flush_ai_batch():
        results = (resolve_segment_batch(ai_queue, ai_client, threshold)
                   if (ai_client is not None and batch_size > 1) else {})
        events = []
        for guid, member, seg_issues in ai_queue:
            res = _plan_segment(guid, member, seg_issues, ai_client, xseg, threshold,
                                ai_result=results.get(guid), ignore_all=ignore_all)
            events.append(_emit(guid, _make_item(guid, member, seg_issues, res)))
        ai_queue.clear()
        if checkpoint is not None:
            checkpoint.flush()
        return events

    for guid in ordered_guids:
        seg_issues = by_seg[guid]
        primary = seg_issues[0]
        member = members.get(guid)

        if checkpoint is not None and checkpoint.has(guid):     # resume: already done
            yield _emit(guid, checkpoint.get_item(guid))
            continue

        if member is None:
            res = Resolution(action="fix", new_target=None, needs_approval=True,
                             strategy="ai", rationale="segment not found; handle manually.")
            item = ResolvedItem(item_id=f"{guid}:{primary.code}", segmentguid=guid,
                                tu_id=primary.tu_id, code=primary.code,
                                problemname=primary.problemname, source_preview="",
                                current_target_preview="", proposed_target_preview=None,
                                resolution=res, issue_count=len(seg_issues))
            yield _emit(guid, item)
            continue

        seg_codes = [normalize_code(i.code) for i in seg_issues]
        if (batch_size > 1 and ai_client is not None
                and _needs_ai_segment(guid, seg_codes, xseg, ignore_all)):
            ai_queue.append((guid, member, seg_issues))
            if len(ai_queue) >= batch_size:
                for ev in _flush_ai_batch():
                    yield ev
            continue

        # deterministic / cached / single-call path -> resolve immediately
        res = _plan_segment(guid, member, seg_issues, ai_client, xseg, threshold,
                            ignore_all=ignore_all)
        yield _emit(guid, _make_item(guid, member, seg_issues, res))

    for ev in _flush_ai_batch():        # last partial batch
        yield ev

    session = ReviewSession(src_lang, tgt_lang, auto, pending,
                            report_only=[], total_issues=total_issues)
    reconcile(session)
    return session


def analyze(content: bytes, ai_client=None, glossary=None, threshold=100,
            batch_size=1, checkpoint=None, ignore_all_codes=None) -> ReviewSession:
    """Run the full analysis (no progress callbacks). Built on analyze_stream."""
    gen = analyze_stream(content, ai_client, glossary, threshold,
                         batch_size=batch_size, checkpoint=checkpoint,
                         ignore_all_codes=ignore_all_codes)
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


def items_for_apply(session, approved_ids, edits=None, ignore_ids=None):
    """Return the ResolvedItems to apply: all auto_applied + the decided pending.

    Each pending segment gets one of three decisions from the UI:
      - approve (confirm AI fix): apply the precomputed resolution as-is;
      - edit (apply human change): the edit is in ⟦id:label⟧ token form — detokenize
        by id back to XML (tags preserved by id even if the user mistypes a label);
        a broken token set falls back to the original so the file is never corrupted;
      - ignore (mark false positive): mark every code on the segment ignored, leaving
        the translation untouched.
    apply() also guards against any stray markers as a final backstop."""
    from xml.sax.saxutils import escape as _xml_escape
    edits = edits or {}
    out = list(session.auto_applied)
    approved_ids = set(approved_ids or ())
    ignore_ids = set(ignore_ids or ())
    for it in session.pending:
        if it.item_id in ignore_ids:
            ign_res = Resolution(action="ignore", new_target=None, needs_approval=False,
                                 strategy=it.resolution.strategy,
                                 rationale="user marked false positive", ignore_codes=[])
            out.append(replace(it, resolution=ign_res))
            continue
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
