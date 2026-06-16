from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Member:
    tu_id: str
    segmentguid: str
    source_text: str            # tokenized (inline tags -> markers)
    target_text: str            # tokenized
    source_tags: dict           # marker -> original tag XML
    target_tags: dict
    status: str
    tm_match: Optional[str]     # target of best <mq:insertedmatch>, if any
    warning_keys: list          # list of (problemname, localizationargs)


@dataclass
class Case:
    id: str
    type: str                   # "target_inconsistency" | "source_inconsistency"
    members: list
    mechanical_diff: str = ""

    @property
    def distinct_sources(self) -> set:
        return {m.source_text for m in self.members}

    @property
    def distinct_targets(self) -> set:
        return {m.target_text for m in self.members}


@dataclass
class Decision:
    case_id: str
    category: str               # false_positive | pick_best | differentiate | needs_manual
    rationale: str
    confidence: str             # high | medium | low
    chosen_member_id: Optional[str] = None
    differentiated: list = field(default_factory=list)  # [{"source_key","new_target"}]


@dataclass
class Issue:
    code: str
    problemname: str
    args: str
    segmentguid: str
    tu_id: str
    outcome: str = "needs_approval"   # ledger bucket: "fix" | "ignore" | "needs_approval"


@dataclass
class Resolution:
    action: str                       # "fix" | "ignore" | "report"
    new_target: Optional[str] = None  # write-ready raw inner XML when target is rewritten
    confidence: float = 0.0
    needs_approval: bool = True
    rationale: str = ""
    strategy: str = ""                # "deterministic" | "ai" | "report_only"
    # Per-code outcomes (conservation): codes on this segment to mark ignored
    # (false positives, e.g. a valid 2016 reorder) IN ADDITION to any target
    # rewrite. Empty + action=="ignore" means "ignore every code on the segment".
    ignore_codes: list = field(default_factory=list)


@dataclass
class ResolvedItem:
    item_id: str                      # f"{segmentguid}:{code}:{index}"
    segmentguid: str
    tu_id: str
    code: str
    problemname: str
    source_preview: str
    current_target_preview: str
    proposed_target_preview: Optional[str]
    resolution: Resolution
    issue_count: int = 1              # number of QA issues this item accounts for (ledger)


@dataclass
class Progress:
    index: int                        # 1-based segment number being processed
    total: int                        # total flagged segments
    tu_id: str
    codes: list                       # normalized codes on this segment
    problem: str                      # primary problem name
    verdict: str                      # "fix" | "ignore" | "needs_approval"


@dataclass
class ReviewSession:
    source_lang: str
    target_lang: str
    auto_applied: list                # list[ResolvedItem]  (apply without asking)
    pending: list                     # list[ResolvedItem]  (need human approval)
    report_only: list                 # list[ResolvedItem]  (informational)
    total_issues: int = 0             # X = count of detected QA issues, for reconcile
