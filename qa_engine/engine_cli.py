import json
from .engine import analyze, apply
from .glossary import load_glossary


def _session_to_dict(rs):
    from .engine import session_to_view
    return session_to_view(rs)


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
