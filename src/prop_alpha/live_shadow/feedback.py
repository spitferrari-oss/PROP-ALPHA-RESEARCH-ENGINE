"""Human feedback capture (extension §78-80): a `TradeProposal` only ever
moves out of `PENDING` through an explicit, attributed human decision —
`apply_feedback` is the single place that transition happens, and it
refuses to move a proposal that has already been decided (extension §76:
a recorded decision is never silently revised — a reviewer who wants to
change their mind creates a new, separate feedback record on a fresh
proposal, not an edit to this one).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from prop_alpha.live_shadow.proposal import ProposalStatus, TradeProposal

_DECISIONS = (ProposalStatus.APPROVED, ProposalStatus.REJECTED)


@dataclass(frozen=True)
class FeedbackRecord:
    proposal_id: str
    timestamp: dt.datetime
    reviewer: str
    decision: ProposalStatus
    rationale: str | None = None


def apply_feedback(
    proposal: TradeProposal,
    decision: ProposalStatus,
    reviewer: str,
    rationale: str | None = None,
    timestamp: dt.datetime | None = None,
) -> tuple[TradeProposal, FeedbackRecord]:
    if decision not in _DECISIONS:
        raise ValueError(f"decision must be one of {_DECISIONS}, got {decision!r}")
    if proposal.status != ProposalStatus.PENDING:
        raise ValueError(
            f"proposal {proposal.proposal_id} is already {proposal.status.value} — a decided proposal is "
            f"never silently revised (extension §76); review a new proposal instead."
        )
    timestamp = timestamp or dt.datetime.now(dt.timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError(
            "timestamp must be timezone-aware — extension §16/§17 require UTC-aware timestamps throughout."
        )

    feedback = FeedbackRecord(
        proposal_id=proposal.proposal_id, timestamp=timestamp, reviewer=reviewer,
        decision=decision, rationale=rationale,
    )
    updated_proposal = replace(proposal, status=decision)
    return updated_proposal, feedback
