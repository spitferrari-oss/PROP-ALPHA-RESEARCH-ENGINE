"""Position Sizing Engine (spec §37).

The backtest engine (`backtest.engine.run_backtest`) always simulates 1
contract — its output is the R-multiple and per-contract dollar P&L for
every trade, which is the right unit for ranking alphas apples-to-apples
(spec §112-113: rank strategies, not money-management choices). Position
sizing is a separate, composable layer applied *after* that: given the
1-contract trade sequence, walk it in time order against an evolving
account and decide how many contracts each trade should have carried.

`prop_aware` sizing enforces spec §37's core constraint: "Il sistema deve
impedire sizing che possa causare breach con una singola perdita
plausibile" — a single stop-out must never, by itself, exceed the
account's remaining daily-loss budget.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from prop_alpha.config import PropFirmConfig

DYNAMIC_RULES = {None, "increase_after_profit", "decrease_after_loss"}


@dataclass
class SizingConfig:
    method: str = "fixed_risk"  # "fixed_contracts" | "fixed_risk"
    fixed_contracts: int = 1
    risk_per_trade_pct: float = 0.005
    max_contracts: int = 20
    prop_aware: bool = True
    dynamic_rule: str | None = None  # None | "increase_after_profit" | "decrease_after_loss"
    dynamic_multiplier: float = 1.5


def _effective_risk_pct(config: SizingConfig, daily_cum_r_so_far: float) -> float:
    if config.dynamic_rule == "increase_after_profit" and daily_cum_r_so_far > 0:
        return config.risk_per_trade_pct * config.dynamic_multiplier
    if config.dynamic_rule == "decrease_after_loss" and daily_cum_r_so_far < 0:
        return config.risk_per_trade_pct / config.dynamic_multiplier
    return config.risk_per_trade_pct


def contracts_for_trade(
    config: SizingConfig,
    equity: float,
    stop_distance_points: float,
    point_value: float,
    daily_cum_r_so_far: float = 0.0,
    remaining_daily_risk_budget: float | None = None,
) -> int:
    """Return the number of contracts for one trade, or 0 if it shouldn't be
    taken at all (no valid stop, or prop-aware sizing zeroes it out).
    """
    if stop_distance_points <= 0 or point_value <= 0:
        return 0

    risk_per_contract = stop_distance_points * point_value

    if config.method == "fixed_contracts":
        contracts = config.fixed_contracts
    else:
        risk_pct = _effective_risk_pct(config, daily_cum_r_so_far)
        risk_dollars = max(equity, 0.0) * risk_pct
        contracts = int(risk_dollars // risk_per_contract)

    contracts = max(0, min(contracts, config.max_contracts))

    if config.prop_aware and remaining_daily_risk_budget is not None:
        affordable = max(0.0, remaining_daily_risk_budget) // risk_per_contract
        contracts = min(contracts, int(affordable))

    return max(contracts, 0)


def apply_position_sizing(
    trades_df: pd.DataFrame,
    config: SizingConfig,
    prop: PropFirmConfig,
    point_value: float,
    timezone: str = "America/New_York",
) -> pd.DataFrame:
    """Walk `trades_df` (1-contract trades, sorted by entry_time) in time
    order, sizing each trade against the account state that would actually
    have existed at that point, and return a copy with `contracts` and
    `pnl` (rescaled by contracts; `pnl` before this call is per-contract,
    since both the gross P&L and the per-contract commission in
    `backtest.engine.run_backtest` scale linearly with contract count).

    A day's remaining risk budget is `max_daily_loss + daily_pnl_so_far`
    (how much more the account can lose today before the daily-loss gate
    trips) — prop-aware sizing caps contracts so one more stop-out can't
    itself blow through that budget.
    """
    if trades_df.empty:
        out = trades_df.copy()
        out["contracts"] = pd.Series(dtype=int)
        return out

    trades_df = trades_df.sort_values("entry_time").reset_index(drop=True)
    day = trades_df["entry_time"].dt.tz_convert(timezone).dt.date

    equity = prop.account_size
    contracts_col = np.zeros(len(trades_df), dtype=int)
    scaled_pnl = np.zeros(len(trades_df))

    current_day = None
    daily_pnl_so_far = 0.0
    daily_cum_r = 0.0

    for i in range(len(trades_df)):
        if day.iloc[i] != current_day:
            current_day = day.iloc[i]
            daily_pnl_so_far = 0.0
            daily_cum_r = 0.0

        row = trades_df.iloc[i]
        stop_distance_points = abs(row["entry_price"] - row["stop_price"])
        remaining_budget = prop.max_daily_loss + daily_pnl_so_far if config.prop_aware else None

        contracts = contracts_for_trade(
            config,
            equity=equity,
            stop_distance_points=stop_distance_points,
            point_value=point_value,
            daily_cum_r_so_far=daily_cum_r,
            remaining_daily_risk_budget=remaining_budget,
        )

        contracts_col[i] = contracts
        pnl = contracts * row["pnl"]
        scaled_pnl[i] = pnl

        equity += pnl
        daily_pnl_so_far += pnl
        if contracts > 0:
            daily_cum_r += row["r_multiple"]

    out = trades_df.copy()
    out["contracts"] = contracts_col
    out["pnl"] = scaled_pnl
    return out
