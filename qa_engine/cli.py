import argparse
import json
import os
import sys
from dataclasses import asdict

from .parser import parse_mqxliff
from .casebuilder import build_cases
from .context import build_case_payload
from .glossary import load_glossary
from .ai import classify_case, build_system_prompt
from .report import write_reports
from .apply import apply_decisions
from .models import Decision
from .whitespace import compute_ws_fixes, normalize_members


def _make_client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def run_analyze(in_path, out_dir, glossary_path, model, client=None, limit=None):
    client = client or _make_client()
    members = parse_mqxliff(in_path)
    ws_fixes = compute_ws_fixes(members)        # detect BEFORE normalizing
    normalize_members(members)                  # collapse pure edge-ws inconsistencies
    cases = build_cases(members)
    if limit:
        cases = cases[:limit]
    glossary = load_glossary(glossary_path)
    gloss_text = "\n".join(f"{k} = {v}" for k, v in glossary.items())
    system_prompt = build_system_prompt(gloss_text)

    decisions = {}
    for case in cases:
        payload = build_case_payload(case, members, glossary)
        try:
            decisions[case.id] = classify_case(client, payload, system_prompt, model)
        except Exception as exc:  # isolate per-case failures
            decisions[case.id] = Decision(case.id, "needs_manual",
                                          f"AI/processing error: {exc}", "low")
    write_reports(cases, decisions, out_dir, ws_fixes=ws_fixes)
    print(f"Analyzed {len(cases)} cases, {len(ws_fixes)} whitespace fixes "
          f"-> {out_dir}/report.html, {out_dir}/decisions.json")
    return cases, decisions, ws_fixes


def run_apply(in_path, decisions_path, out_path, include_low, force):
    if os.path.exists(out_path) and not force:
        raise SystemExit(f"{out_path} exists; use --force to overwrite.")
    members = parse_mqxliff(in_path)
    normalize_members(members)
    cases = build_cases(members)
    with open(decisions_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    # new format: {"whitespace_fixes": [...], "decisions": {...}}; fall back to flat
    ws_fixes = raw.get("whitespace_fixes", []) if isinstance(raw, dict) else []
    raw_decisions = raw.get("decisions", raw) if isinstance(raw, dict) else raw

    decisions = {}
    skipped_low = 0
    for cid, d in raw_decisions.items():
        if d.get("confidence") == "low" and not include_low:
            skipped_low += 1
            continue
        decisions[cid] = Decision(
            case_id=d["case_id"], category=d["category"], rationale=d["rationale"],
            confidence=d["confidence"], chosen_member_id=d.get("chosen_member_id"),
            differentiated=d.get("differentiated", []),
        )
    skipped = apply_decisions(in_path, decisions, cases, out_path, ws_fixes=ws_fixes)
    print(f"Applied {len(decisions)} decisions, {len(ws_fixes)} whitespace fixes -> {out_path}"
          + (f" ({skipped_low} low-confidence skipped)" if skipped_low else ""))
    for case_id, tu_id, reason in skipped:
        print(f"  WARNING: case {case_id} segment {tu_id} left unchanged (tag mismatch): {reason}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="qa_engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze")
    a.add_argument("input")
    a.add_argument("--out-dir", default="out")
    a.add_argument("--glossary", default=None)
    a.add_argument("--model", default="claude-opus-4-8")
    a.add_argument("--limit", type=int, default=None)

    ap = sub.add_parser("apply")
    ap.add_argument("input")
    ap.add_argument("decisions")
    ap.add_argument("--out", default=None)
    ap.add_argument("--include-low", action="store_true")
    ap.add_argument("--force", action="store_true")

    args = p.parse_args(argv)
    if args.cmd == "analyze":
        run_analyze(args.input, args.out_dir, args.glossary, args.model, limit=args.limit)
    else:
        out = args.out or args.input.replace(".mqxliff", ".FIXED.mqxliff")
        run_apply(args.input, args.decisions, out, args.include_low, args.force)


if __name__ == "__main__":
    main(sys.argv[1:])
