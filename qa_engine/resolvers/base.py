from ..models import Resolution


def normalize_code(code: str) -> str:
    """memoQ codes appear as zero-padded ('03050'); normalize to plain int string."""
    try:
        return str(int(code))
    except (TypeError, ValueError):
        return code or ""


class Resolver:
    strategy = "report_only"

    def resolve(self, issue, member, context) -> Resolution:
        raise NotImplementedError


class ReportOnlyResolver(Resolver):
    strategy = "report_only"

    def resolve(self, issue, member, context) -> Resolution:
        return Resolution(
            action="report",
            new_target=None,
            confidence=0.0,
            needs_approval=True,
            rationale=f"Code {normalize_code(issue.code)} ({issue.problemname}) "
                      f"is not auto-resolvable; left for human review.",
            strategy="report_only",
        )
