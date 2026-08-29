"""Walk-Forward Analysis (spec §26).

Current strategies are fixed-rule (no fitted parameters), so there is no
"train" step to re-fit on each window — what this validates is *temporal
stability*: does the rule's edge hold up as we roll forward through
sequential, non-overlapping out-of-time folds, or was the full-sample
result carried by one lucky stretch? A parameterized/ML strategy would
extend this with an actual fit-on-train step per fold; the fold-splitting
and aggregation machinery here already supports that (folds only ever see
their own days).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.backtest.engine import run_backtest, trades_to_frame
from prop_alpha.backtest.metrics import compute_day_metrics
from prop_alpha.strategies.base import Strategy


def _session_day(df: pd.DataFrame, timezone: str) -> pd.Series:
    return df["timestamp"].dt.tz_convert(timezone).dt.date


def make_folds(df: pd.DataFrame, n_folds: int, timezone: str = "America/New_York") -> list[list]:
    """Split the dataset's trading days into `n_folds` sequential,
    non-overlapping, (approximately) equal-length day blocks in chronological
    order — a rolling/expanding split isn't needed here since there's no
    train step, just a forward walk through time.
    """
    days = sorted(_session_day(df, timezone).unique())
    if n_folds < 1 or len(days) < n_folds:
        return [days] if days else []
    fold_size = len(days) // n_folds
    folds = [days[i * fold_size:(i + 1) * fold_size] for i in range(n_folds - 1)]
    folds.append(days[(n_folds - 1) * fold_size:])  # last fold absorbs the remainder
    return [f for f in folds if f]


def run_walk_forward(
    strategy: Strategy,
    df_feat: pd.DataFrame,
    cost_model: CostModel,
    max_trades_day: int,
    point_value: float,
    n_folds: int = 5,
    timezone: str = "America/New_York",
) -> dict:
    """Backtest `strategy` independently within each sequential fold (no
    feature recomputation — df_feat's rolling/session features are already
    computed over the full history, folds only filter which day's *rows*
    are handed to the backtester) and summarize cross-fold stability.
    """
    day = _session_day(df_feat, timezone)
    folds = make_folds(df_feat, n_folds, timezone)

    fold_ev_per_day: list[float] = []
    for fold_days in folds:
        fold_df = df_feat[day.isin(fold_days)]
        if fold_df.empty:
            fold_ev_per_day.append(np.nan)
            continue
        df_signals = strategy.with_risk_levels(fold_df)
        trades = run_backtest(df_signals, cost_model, max_trades_day=max_trades_day, point_value=point_value)
        trades_df = trades_to_frame(trades)
        metrics = compute_day_metrics(trades_df)
        fold_ev_per_day.append(metrics["ev_per_day_dollars"])

    valid = [v for v in fold_ev_per_day if not (v is None or np.isnan(v))]
    n_valid = len(valid)
    positive_fraction = (sum(1 for v in valid if v > 0) / n_valid) if n_valid else np.nan

    return {
        "n_folds": len(folds),
        "fold_ev_per_day": fold_ev_per_day,
        "positive_fold_fraction": positive_fraction,
        "fold_ev_std": float(np.std(valid)) if n_valid > 1 else np.nan,
        "worst_fold_ev_per_day": float(min(valid)) if valid else np.nan,
    }
