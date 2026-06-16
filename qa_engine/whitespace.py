import re
from .tags import detokenize

_MARK = re.compile(r'⟦\d+⟧')
_LEAD = re.compile(r'^[ \t]*')
_TRAIL = re.compile(r'[ \t]*$')


def lead_ws(text: str) -> str:
    return _LEAD.match(text).group(0)


def trail_ws(text: str) -> str:
    return _TRAIL.search(text).group(0)


def _split(tok: str):
    """(text_parts[n+1], markers[n]) for a tokenized string."""
    return _MARK.split(tok), _MARK.findall(tok)


def align_whitespace(src_tok: str, tgt_tok: str) -> str:
    """Set each inter-tag text run's leading/trailing [ \\t] in the target equal
    to the source's corresponding run. Returns the target unchanged when the
    marker counts differ (cannot safely align). Inter-word spaces and non-[ \\t]
    characters (e.g. nbsp) are preserved."""
    s_parts, s_marks = _split(src_tok)
    t_parts, t_marks = _split(tgt_tok)
    if len(s_marks) != len(t_marks):
        return tgt_tok
    new_parts = []
    for i, t in enumerate(t_parts):
        s = s_parts[i]
        core = _TRAIL.sub('', _LEAD.sub('', t))
        new_parts.append(lead_ws(s) + core + trail_ws(s))
    out = new_parts[0]
    for mk, part in zip(t_marks, new_parts[1:]):
        out += mk + part
    return out


def compute_ws_fixes(members: list) -> list:
    """Fixes for members whose target whitespace doesn't match the source's
    tag-boundary whitespace."""
    fixes = []
    for m in members:
        new_tok = align_whitespace(m.source_text, m.target_text)
        if new_tok != m.target_text:
            fixes.append({
                "tu_id": m.tu_id,
                "segmentguid": m.segmentguid,
                "new_target_inner": detokenize(new_tok, m.target_tags),
                "old_preview": m.target_text,
                "new_preview": new_tok,
            })
    return fixes


def normalize_members(members: list) -> list:
    """In place: align each target's tag-boundary whitespace to its source's."""
    for m in members:
        m.target_text = align_whitespace(m.source_text, m.target_text)
    return members
