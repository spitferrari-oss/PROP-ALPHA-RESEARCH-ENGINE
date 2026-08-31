"""`TradeProposal` (extension §75-77): a logged, human-reviewable record
of what the system would propose — never an executed or executable order.
`make_proposal` is the only constructor; it stamps a deterministic
`proposal_id` (a hash of the fields that make a proposal unique) so the
same proposal built twice from the same inputs is recognizably the same
proposal, not a fabricated new one.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

from prop_alpha.market_state.vector import MarketState
from prop_alpha.utils.hashing import hash_dict

_DIRECTIONS = ("LONG", "SHORT")


class ProposalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class TradeProposal:
    proposal_id: str
    timestamp: dt.datetime
    instrument: str
    direction: str
    entry_price: float
    rationale: str
    stop_price: float | None = None
    target_price: float | None = None
    expected_r: float | None = None
    model_probability: float | None = None
    market_state_snapshot: dict = field(default_factory=dict)
    status: ProposalStatus = ProposalStatus.PENDING


def make_proposal(
    timestamp: dt.datetime,
    instrument: str,
    direction: str,
    entry_price: float,
    rationale: str,
    stop_price: float | None = None,
    target_price: float | None = None,
    expected_r: float | None = None,
    model_probability: float | None = None,
    market_state: MarketState | None = None,
) -> TradeProposal:
    if timestamp.tzinfo is None:
        raise ValueError(
            "timestamp must be timezone-aware — extension §16/§17 require UTC-aware timestamps throughout."
        )
    if direction not in _DIRECTIONS:
        raise ValueError(f"direction must be one of {_DIRECTIONS}, got {direction!r}")

    market_state_snapshot = market_state.as_flat_dict() if market_state is not None else {}
    proposal_id = hash_dict({
        "timestamp": timestamp,
        "instrument": instrument,
        "direction": direction,
        "entry_price": entry_price,
        "rationale": rationale,
    })

    return TradeProposal(
        proposal_id=proposal_id,
        timestamp=timestamp,
        instrument=instrument,
        direction=direction,
        entry_price=entry_price,
        rationale=rationale,
        stop_price=stop_price,
        target_price=target_price,
        expected_r=expected_r,
        model_probability=model_probability,
        market_state_snapshot=market_state_snapshot,
        status=ProposalStatus.PENDING,
    )


def proposal_from_record(record: dict) -> TradeProposal:
    """Reconstructs a `TradeProposal` from a `LiveShadowLedger.
    read_proposals()` row — the inverse of `dataclasses.asdict`, needed
    wherever a caller (e.g. a CLI review command) reads proposals back out
    of the ledger and must apply feedback against a real `TradeProposal`
    rather than a loose dict.
    """
    fields = dict(record)
    fields.pop("kind", None)
    fields["timestamp"] = dt.datetime.fromisoformat(fields["timestamp"])
    fields["status"] = ProposalStatus(fields["status"])
    return TradeProposal(**fields)
