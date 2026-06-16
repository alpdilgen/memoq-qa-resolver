import re

# Order matters: match ph (with its content) and self-closing tags before
# the generic paired-g open/close.
_TAG_RE = re.compile(
    r'<bpt\b[^>]*>.*?</bpt>'    # paired begin-tag, opaque (escaped catalog value)
    r'|<ept\b[^>]*>.*?</ept>'   # paired end-tag, opaque
    r'|<it\b[^>]*>.*?</it>'     # isolated tag, opaque
    r'|<ph\b[^>]*>.*?</ph>'     # ph wraps original-format codes -> opaque
    r'|<x\b[^>]*/>'             # self-closing placeholder
    r'|<mq:ch\b[^>]*/>'        # self-closing memoQ char
    r'|<g\b[^>]*>'             # paired open
    r'|</g>',                   # paired close
    re.DOTALL,
)

_OPEN, _CLOSE = "⟦", "⟧"   # ⟦ ⟧  private-ish brackets unlikely in text
_MARK_RE = re.compile(_OPEN + r"(\d+)" + _CLOSE)


def tokenize(xml_text: str):
    """Replace inline tags with ordered markers ⟦N⟧. Returns (text, {marker: xml})."""
    mapping = {}
    counter = [0]

    def repl(m):
        counter[0] += 1
        marker = f"{_OPEN}{counter[0]}{_CLOSE}"
        mapping[marker] = m.group(0)
        return marker

    return _TAG_RE.sub(repl, xml_text), mapping


def markers_in(text: str) -> set:
    return {f"{_OPEN}{n}{_CLOSE}" for n in _MARK_RE.findall(text)}


def detokenize(text: str, mapping: dict) -> str:
    """Restore original tags. Raises ValueError if markers don't match mapping."""
    if markers_in(text) != set(mapping.keys()):
        raise ValueError(
            f"marker mismatch: text has {markers_in(text)}, mapping has {set(mapping)}"
        )
    out = text
    for marker, xml in mapping.items():
        out = out.replace(marker, xml)
    return out
