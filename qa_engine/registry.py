from .resolvers.base import ReportOnlyResolver, normalize_code

# Code -> strategy label. Resolvers are attached in Task 6/7; until then a code
# mapped to deterministic/ai with no registered resolver falls back to report_only.
STRATEGY_BY_CODE = {
    # deterministic whitespace family
    "3050": "deterministic", "3071": "deterministic", "3072": "deterministic",
    "3073": "deterministic", "3074": "deterministic", "3075": "deterministic",
    "3076": "deterministic", "3110": "deterministic", "3190": "deterministic",
    "3191": "deterministic", "3192": "deterministic", "3193": "deterministic",
    "3194": "deterministic", "3195": "deterministic", "3196": "deterministic",
    "3197": "deterministic",
    # ai
    "3100": "ai", "3101": "ai",
    # report_only (Phase 1a leaves these for humans)
    "3161": "report_only", "3162": "report_only", "3081": "report_only",
    "3082": "report_only", "3083": "report_only", "3084": "report_only",
}

# Resolver instances are registered here by the engine bootstrap (Task 8).
_RESOLVERS = {}


def register_resolver(code: str, resolver):
    _RESOLVERS[normalize_code(code)] = resolver


def get_resolver(issue):
    return _RESOLVERS.get(normalize_code(issue.code), ReportOnlyResolver())
