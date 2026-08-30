"""Risk Agent (spec §58): checks whether the account-facing mechanics
actually work for this alpha — can position sizing size any real
contracts under the account's risk budget, and does the raw trade-sequence
drawdown stay within what the prop firm's rules would tolerate — as
distinct from the Statistician's Monte-Carlo-based P(breach)/P(payout)
checks, which are about simulated *paths*, not this single realized one.
"""
from __future__ import annotations

from prop_alpha.agents.gates import Gate
from prop_alpha.config import PropFirmConfig


def evaluate_risk_gates(
    alpha_result: dict,
    payout_optimizer_results: list[dict] | None,
    prop: PropFirmConfig,
) -> list[Gate]:
    gates: list[Gate] = []

    if payout_optimizer_results:
        max_trades = max((p.get("n_trades", 0) for p in payout_optimizer_results), default=0)
        sizeable = max_trades > 0
        gates.append(Gate(
            "SIZING_FEASIBLE", "PASS" if sizeable else "FAIL",
            f"best of {len(payout_optimizer_results)} sizing/stop policies sized {max_trades} trades "
            f"— {'position sizing can afford at least 1 contract' if sizeable else 'risk budget cannot afford even 1 contract at this account size/instrument'}",
        ))
    else:
        gates.append(Gate("SIZING_FEASIBLE", "NOT_EVALUATED", "No Payout Optimizer results available."))

    max_drawdown = alpha_result.get("max_drawdown")
    if max_drawdown is not None and max_drawdown == max_drawdown:
        within_limits = abs(max_drawdown) <= prop.max_total_loss
        gates.append(Gate(
            "DRAWDOWN_WITHIN_LIMITS", "PASS" if within_limits else "FAIL",
            f"realized max drawdown ${max_drawdown:.0f} vs. account max_total_loss ${prop.max_total_loss:.0f}",
        ))
    else:
        gates.append(Gate("DRAWDOWN_WITHIN_LIMITS", "NOT_EVALUATED", "max_drawdown unavailable."))

    return gates
