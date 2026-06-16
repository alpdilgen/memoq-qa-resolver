import json
from dataclasses import asdict
from .engine import analyze, apply
from .glossary import load_glossary


def _session_to_dict(rs):
    def items(bucket):
        return [
            {
                "item_id": it.item_id, "segmentguid": it.segmentguid, "tu_id": it.tu_id,
                "code": it.code, "problemname": it.problemname,
                "source": it.source_preview, "current_target": it.current_target_preview,
                "proposed_target": it.proposed_target_preview,
                **asdict(it.resolution),
            } for it in bucket
        ]
    return {
        "source_lang": rs.source_lang, "target_lang": rs.target_lang,
        "auto_applied": items(rs.auto_applied),
        "pending": items(rs.pending),
        "report_only": items(rs.report_only),
    }


def run_qa_analyze(in_path, out_path, ai_client=None, glossary_path=None):
    content = open(in_path, "rb").read()
    glossary = load_glossary(glossary_path)
    rs = analyze(content, ai_client=ai_client, glossary=glossary)
    data = _session_to_dict(rs)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    counts = {k: len(data[k]) for k in ("auto_applied", "pending", "report_only")}
    print(f"Analyzed: {counts}")
    return {"counts": counts}
