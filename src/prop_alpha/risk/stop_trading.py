"""Stop-Trading Policy Engine (spec §39).

Searches over policies of the form "stop after +NR / stop after N losses /
stop after -NR", measuring what they do to **Payout**, not raw Return
(spec §39: "L'algoritmo deve misurare Payout_policy non semplicemente
Return_policy" — that comparison happens in `payout_optimizer.py`, which
runs the filtered trade stream back through the prop simulator). This
module only decides which trades a policy would have skipped.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class StopTradingPolicy:
    name: str
    stop_after_profit_r: float | None = None  # stop for the day once cumulative R >= this
    stop_after_loss_r: float | None = None    # stop for the day once cumulative R <= -this
    stop_after_n_losses: int | None = None    # stop for the day after this many losing trades

    def describe(self) -> str:
        parts = []
        if self.stop_after_profit_r is not None:
            parts.append(f"stop after +{self.stop_after_profit_r}R")
        if self.stop_after_loss_r is not None:
            parts.append(f"stop after -{self.stop_after_loss_r}R")
        if self.stop_after_n_losses is not None:
            parts.append(f"stop after {self.stop_after_n_losses} losses")
        return ", ".join(parts) if parts else "no stop-trading rule"


def apply_day_policy(
    trades_df: pd.DataFrame,
    policy: StopTradingPolicy,
    timezone: str = "America/New_York",
) -> pd.DataFrame:
    """Walk `trades_df` in time order and drop every trade that would occur
    after the policy's stop condition has already fired that day. A trade
    that itself triggers the condition is kept — the policy stops trading
    *after* it, not retroactively.
    """
    if trades_df.empty:
        return trades_df.copy()

    trades_df = trades_df.sort_values("entry_time").reset_index(drop=True)
    day = trades_df["entry_time"].dt.tz_convert(timezone).dt.date

    keep = [True] * len(trades_df)
    current_day = None
    cum_r = 0.0
    n_losses = 0
    stopped = False

    for i in range(len(trades_df)):
        if day.iloc[i] != current_day:
            current_day = day.iloc[i]
            cum_r = 0.0
            n_losses = 0
            stopped = False

        if stopped:
            keep[i] = False
            continue

        row = trades_df.iloc[i]
        cum_r += row["r_multiple"]
        if row["pnl"] <= 0:
            n_losses += 1

        if policy.stop_after_profit_r is not None and cum_r >= policy.stop_after_profit_r:
            stopped = True
        if policy.stop_after_loss_r is not None and cum_r <= -policy.stop_after_loss_r:
            stopped = True
        if policy.stop_after_n_losses is not None and n_losses >= policy.stop_after_n_losses:
            stopped = True

    return trades_df[pd.Series(keep, index=trades_df.index)].reset_index(drop=True)
