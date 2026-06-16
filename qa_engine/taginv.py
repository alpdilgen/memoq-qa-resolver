"""Inline-tag inventory + per-code safety rules over tokenized text (⟦id:label⟧).

The cardinal invariant: a proposed target may NEVER introduce an inline tag that is
absent from the source (no foreign tags), and tag-structure codes have count rules:
  - 2016 (order changed): multisets equal  -> false positive (order may differ)
  - 2011 missing / 2015 extra: fix must reach count parity with the source
The tag "kind" is the readable label (e.g. '<cf bold=True size=10>', '</cf>', 'ph'),
which is stable across reordering; volatile numeric ids are ignored.
"""
import re
from collections import Counter

_TOKEN_RE = re.compile(r"⟦\d+:(.*?)⟧")


def tag_multiset(tok_text: str) -> Counter:
    """Counter of inline-tag kinds (by readable label) in a tokenized segment."""
    return Counter(_TOKEN_RE.findall(tok_text or ""))


def no_foreign_tags(proposed_tok: str, source_tok: str) -> bool:
    """True if every tag kind in the proposal exists in the source with a count
    not exceeding the source's (never invents or duplicates a tag beyond source)."""
    src = tag_multiset(source_tok)
    for kind, n in tag_multiset(proposed_tok).items():
        if n > src.get(kind, 0):
            return False
    return True


def count_parity(proposed_tok: str, source_tok: str) -> bool:
    """True if the proposal's tag multiset equals the source's."""
    return tag_multiset(proposed_tok) == tag_multiset(source_tok)


def tag_verdict_2016(target_tok: str, source_tok: str) -> bool:
    """2016 (changed tag order) is a false positive when all source tags are
    present in the target (multisets equal) — the order may differ for the
    target language's word order."""
    return count_parity(target_tok, source_tok)
