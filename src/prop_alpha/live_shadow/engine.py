"""Ties a market-state stream (Phase L, fed by either a live subscription
or Phase N's deterministic replay) to proposal generation and logging
(extension §59). `run_live_shadow_session` owns none of the trading logic
itself — `proposal_generator` is caller-supplied, so this module makes no
claim about which strategy, alpha, or condition produced a proposal; it
only guarantees that every non-`None` proposal returned gets logged to
the ledger before the session moves on, so nothing a generator proposes
goes unrecorded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from prop_alpha.live_shadow.ledger import LiveShadowLedger
from prop_alpha.live_shadow.proposal import TradeProposal
from prop_alpha.market_state.vector import MarketState

ProposalGenerator = Callable[[MarketState], TradeProposal | None]


@dataclass(frozen=True)
class LiveShadowSessionResult:
    n_market_states: int
    n_proposals: int
    proposals: list[TradeProposal] = field(default_factory=list)


def run_live_shadow_session(
    market_states: Iterable[MarketState],
    proposal_generator: ProposalGenerator,
    ledger: LiveShadowLedger,
) -> LiveShadowSessionResult:
    n_market_states = 0
    proposals: list[TradeProposal] = []
    for state in market_states:
        n_market_states += 1
        proposal = proposal_generator(state)
        if proposal is None:
            continue
        ledger.record_proposal(proposal)
        proposals.append(proposal)

    return LiveShadowSessionResult(
        n_market_states=n_market_states, n_proposals=len(proposals), proposals=proposals,
    )
