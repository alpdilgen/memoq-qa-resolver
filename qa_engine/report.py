import json
import html
import os
from collections import Counter
from dataclasses import asdict


def write_reports(cases, decisions, out_dir, ws_fixes=None):
    ws_fixes = ws_fixes or []
    os.makedirs(out_dir, exist_ok=True)
    _write_json(decisions, ws_fixes, os.path.join(out_dir, "decisions.json"))
    _write_html(cases, decisions, ws_fixes, os.path.join(out_dir, "report.html"))


def _write_json(decisions, ws_fixes, path):
    data = {
        "whitespace_fixes": ws_fixes,
        "decisions": {cid: asdict(d) for cid, d in decisions.items()},
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _esc(s):
    return html.escape(str(s))



def _write_html(cases, decisions, ws_fixes, path):
    counts = Counter(d.category for d in decisions.values())
    case_by_id = {c.id: c for c in cases}

    rows = []
    for cid, d in decisions.items():
        c = case_by_id.get(cid)
        seg_ids = ", ".join(m.tu_id for m in c.members) if c else ""
        sources = "<br>".join(_esc(s) for s in sorted(c.distinct_sources)) if c else ""
        targets = "<br>".join(_esc(t) for t in sorted(c.distinct_targets)) if c else ""
        diff = _esc(c.mechanical_diff) if c else ""
        rows.append(f"""
        <tr class="{_esc(d.category)}">
          <td>{_esc(cid)}</td>
          <td>{_esc(d.category)}</td>
          <td>{_esc(d.confidence)}</td>
          <td>{seg_ids}</td>
          <td><b>diff:</b> {diff}<br><b>sources:</b><br>{sources}<br>
              <b>targets:</b><br>{targets}</td>
          <td>{_esc(d.rationale)}</td>
        </tr>""")

    ws_rows = []
    for f in ws_fixes:
        ws_rows.append(f"""
        <tr><td>{_esc(f['tu_id'])}</td>
            <td><code>{_esc(f['old_preview'])}</code></td>
            <td><code>{_esc(f['new_preview'])}</code></td></tr>""")

    summary = " &nbsp; ".join(f"{cat}: {n}" for cat, n in sorted(counts.items()))
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Inconsistency Resolver Report</title>
<style>
 body{{font-family:sans-serif;margin:2rem}}
 table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
 td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;font-size:13px}}
 tr.false_positive{{background:#f3faf3}}
 tr.differentiate{{background:#fff6e6}}
 tr.pick_best{{background:#eef3fb}}
 tr.needs_manual{{background:#fdecec}}
</style></head><body>
<h1>Inconsistency Resolver Report</h1>
<p><b>Decisions summary:</b> {summary}</p>
<p><b>Whitespace fixes (target edge = source edge):</b> {len(ws_fixes)}</p>
<h2>Whitespace fixes</h2>
<table>
<tr><th>Segment</th><th>Before</th><th>After</th></tr>
{''.join(ws_rows)}
</table>
<h2>Inconsistency decisions</h2>
<table>
<tr><th>Case</th><th>Category</th><th>Confidence</th><th>Segments</th>
    <th>Diff / Sources / Targets</th><th>Rationale</th></tr>
{''.join(rows)}
</table></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
