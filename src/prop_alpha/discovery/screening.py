"""Quick candidate screening: a cheap IS/OOS backtest (no bootstrap, Monte
Carlo, walk-forward, or cost-sensitivity — those are the expensive Phase 4
gates a promoted candidate goes through via `research full-run`, not
something to run for every one of ~150 combinatorial candidates).

A candidate "passes" only as a coarse pre-filter: enough trades to mean
anything, and positive EV/day on *both* the in-sample and out-of-sample
slices — requiring both guards against an IS-only fluke without pretending
this is full statistical validation.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.backtest.engine import run_backtest, trades_to_frame
from prop_alpha.backtest.metrics import compute_day_metrics, compute_trade_metrics
from prop_alpha.config import EngineConfig
from prop_alpha.discovery.setup_generator import GeneratedStrategy


def quick_evaluate(
    strategy: GeneratedStrategy,
    df_feat: pd.DataFrame,
    cost_model: CostModel,
    config: EngineConfig,
    oos_start_day,
) -> dict:
    df_signals = strategy.with_risk_levels(df_feat)
    trades = run_backtest(
        df_signals, cost_model=cost_model,
        max_trades_day=config.risk.max_trades_day, point_value=config.market.point_value,
    )
    trades_df = trades_to_frame(trades)

    trade_metrics = compute_trade_metrics(trades_df)

    if trades_df.empty:
        is_ev_day = float("nan")
        oos_ev_day = float("nan")
    else:
        is_trades = trades_df[trades_df["exit_time"].dt.date < oos_start_day]
        oos_trades = trades_df[trades_df["exit_time"].dt.date >= oos_start_day]
        is_ev_day = compute_day_metrics(is_trades)["ev_per_day_dollars"]
        oos_ev_day = compute_day_metrics(oos_trades)["ev_per_day_dollars"]

    n_trades = trade_metrics["n_trades"]
    passed = (
        n_trades >= config.discovery.min_trades_to_screen
        and is_ev_day == is_ev_day and is_ev_day > 0  # not NaN and positive
        and oos_ev_day == oos_ev_day and oos_ev_day > 0
    )

    return {
        "alpha_id": strategy.meta.alpha_id,
        "alpha_name": strategy.meta.alpha_name,
        "mechanism": strategy.meta.mechanism,
        "n_trades": n_trades,
        "win_rate": trade_metrics["win_rate"],
        "ev_per_trade_dollars": trade_metrics["ev_per_trade_dollars"],
        "is_ev_per_day": is_ev_day,
        "oos_ev_per_day": oos_ev_day,
        "passed_screen": passed,
    }
