from ..models import Resolution
from ..whitespace import align_whitespace, collapse_internal_spaces
from ..tags import detokenize, _TOKEN_RE
from .base import Resolver


class WhitespaceResolver(Resolver):
    """Deterministic: align the target's tag-boundary/edge whitespace to the
    source and collapse internal multi-space runs (3050). Covers codes 3050,
    3110, 3190-3193. Zero-error by construction (only [ \t] adjacent to
    tags/edges, or runs of 2+ between words, are changed)."""

    strategy = "deterministic"

    def resolve(self, issue, member, context) -> Resolution:
        new_tok = collapse_internal_spaces(align_whitespace(member.source_text, member.target_text))
        if new_tok == member.target_text:
            return Resolution(
                action="report", new_target=None, confidence=1.0,
                needs_approval=False, strategy="deterministic",
                rationale="No target whitespace difference vs source for this code.",
            )
        if member.target_tags:
            new_inner = detokenize(new_tok, member.target_tags)
        else:
            new_inner = _TOKEN_RE.sub("", new_tok)
        return Resolution(
            action="fix", new_target=new_inner, confidence=1.0,
            needs_approval=False, strategy="deterministic",
            rationale="Aligned target tag-boundary/edge whitespace to the source.",
        )
