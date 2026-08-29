"""Prop path simulator: day-by-day account simulation over Monte Carlo P&L
paths (spec §33 Risk of Ruin, §38 Payout Optimizer, §67 Expected Payout
Distribution, §68 Prop Path Simulator).

Every account rule (daily loss limit, trailing/static drawdown, profit
target, minimum trading days) is read from a configurable PropFirmConfig —
nothing here is hardcoded to one specific prop firm's rules.
"""
from __future__ import annotations

import numpy as np

from prop_alpha.config import PropFirmConfig


def simulate_prop_paths(pnl_paths: np.ndarray, prop: PropFirmConfig) -> dict:
    """`pnl_paths` is an (n_paths, n_days) array of simulated daily P&L in
    dollars (e.g. from statistics.monte_carlo.simulate_daily_pnl_paths).

    Returns aggregate P(breach), P(payout), expected payout, and the
    terminal-balance distribution across all simulated account paths.
    """
    n_paths, n_days = pnl_paths.shape
    breached = np.zeros(n_paths, dtype=bool)
    paid_out = np.zeros(n_paths, dtype=bool)
    days_to_payout = np.full(n_paths, np.nan)
    terminal_balance = np.zeros(n_paths)

    for p in range(n_paths):
        balance = prop.account_size
        high_watermark = prop.account_size
        for d in range(n_days):
            daily_pnl = pnl_paths[p, d]
            balance += daily_pnl
            trading_day_count = d + 1

            if daily_pnl <= -prop.max_daily_loss:
                breached[p] = True
                break

            if prop.trailing_drawdown:
                floor = high_watermark - prop.max_total_loss
            else:
                floor = prop.account_size - prop.max_total_loss
            if balance <= floor:
                breached[p] = True
                break

            high_watermark = max(high_watermark, balance)

            total_profit = balance - prop.account_size
            if (
                total_profit >= prop.profit_target
                and trading_day_count >= prop.minimum_trading_days
            ):
                paid_out[p] = True
                days_to_payout[p] = trading_day_count
                break

        terminal_balance[p] = balance

    p_breach = float(breached.mean())
    p_payout = float(paid_out.mean())
    expected_payout = float(p_payout * prop.payout_threshold)
    valid_days = days_to_payout[~np.isnan(days_to_payout)]

    return {
        "n_paths": n_paths,
        "n_days_horizon": n_days,
        "p_breach": p_breach,
        "p_payout": p_payout,
        "expected_payout": expected_payout,
        "expected_days_to_payout": float(valid_days.mean()) if len(valid_days) else np.nan,
        "terminal_balance_p5": float(np.percentile(terminal_balance, 5)),
        "terminal_balance_p50": float(np.percentile(terminal_balance, 50)),
        "terminal_balance_p95": float(np.percentile(terminal_balance, 95)),
    }
