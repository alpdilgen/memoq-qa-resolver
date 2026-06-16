import re
import html

_TAG_RE = re.compile(
    r'<bpt\b[^>]*>.*?</bpt>'
    r'|<ept\b[^>]*>.*?</ept>'
    r'|<it\b[^>]*>.*?</it>'
    r'|<ph\b[^>]*>.*?</ph>'
    r'|<x\b[^>]*/>'
    r'|<mq:ch\b[^>]*/>'
    r'|<g\b[^>]*>'
    r'|</g>',
    re.DOTALL,
)

_OPEN, _CLOSE = "⟦", "⟧"
# token: ⟦<id>:<label>⟧ — id is authoritative, label is decorative/readable
_TOKEN_RE = re.compile(_OPEN + r"(\d+):.*?" + _CLOSE)
_CATALOG_RE = re.compile(r'mmq78catalogvalue=(?:&quot;|")(.*?)(?:&quot;|")')
_NAME_RE = re.compile(r'</?\s*([A-Za-z][\w:.-]*)')


def tag_label(tag_xml: str) -> str:
    """memoQ-style readable label for an inline tag, from mmq78catalogvalue
    (double-unescaped); fall back to the tag's local name."""
    m = _CATALOG_RE.search(tag_xml)
    if m:
        lbl = html.unescape(html.unescape(m.group(1))).strip()
        if lbl:
            return lbl if lbl.startswith("<") else f"<{lbl}>"
    name = _NAME_RE.search(tag_xml)
    nm = name.group(1) if name else "tag"
    if tag_xml.lstrip().startswith("</"):
        return f"</{nm}>"
    if tag_xml.rstrip().endswith("/>"):
        return f"<{nm}/>"
    return f"<{nm}>"


def tokenize(xml_text: str):
    """Replace inline tags with readable tokens ⟦id:label⟧. Returns (text, {id: xml})."""
    mapping = {}
    counter = [0]

    def repl(m):
        counter[0] += 1
        i = counter[0]
        mapping[str(i)] = m.group(0)
        return f"{_OPEN}{i}:{tag_label(m.group(0))}{_CLOSE}"

    return _TAG_RE.sub(repl, xml_text), mapping


def markers_in(text: str) -> set:
    return set(_TOKEN_RE.findall(text))


def to_chips(text: str) -> str:
    """Render a segment for human display: inline tags (raw XML or ⟦id:label⟧
    tokens) become memoQ-style chips like [<cf size=9.5>] / [</strong>]. Used by
    the UI only — never for the write-back path."""
    text = _TOKEN_RE.sub(lambda m: f"[{m.group(0).split(':', 1)[1][:-1]}]", text)
    return _TAG_RE.sub(lambda m: f"[{tag_label(m.group(0))}]", text)


def detokenize(text: str, mapping: dict) -> str:
    """Restore tags by id. Raises ValueError if the ids present don't match mapping."""
    if markers_in(text) != set(mapping.keys()):
        raise ValueError(f"token id mismatch: text {markers_in(text)} vs mapping {set(mapping)}")
    return _TOKEN_RE.sub(lambda m: mapping[m.group(1)], text)
