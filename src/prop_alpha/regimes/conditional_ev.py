"""Conditional Expected Value Engine (spec §14): "quando un'idea funziona,
non soltanto se funziona" — break a strategy's trades down by the regime
active at each trade's entry bar, so a strategy that looks flat overall but
is actually strong in one regime and weak in another doesn't get discarded
(or, worse, traded blindly in the regime where it doesn't work).
"""
from __future__ import annotations

import pandas as pd


def conditional_ev_by_regime(
    trades_df: pd.DataFrame,
    df_feat: pd.DataFrame,
    regime_col: str = "regime_rule",
) -> pd.DataFrame:
    """Join each trade to the regime active at its entry bar and aggregate.
    Returns one row per regime, sorted by EV/trade descending.
    """
    columns = [regime_col, "n_trades", "win_rate", "avg_r", "ev_dollars"]
    if trades_df.empty:
        return pd.DataFrame(columns=columns)

    merged = trades_df.merge(
        df_feat[["timestamp", regime_col]],
        left_on="entry_time", right_on="timestamp", how="left",
    )
    merged[regime_col] = merged[regime_col].fillna("UNKNOWN")

    grouped = merged.groupby(regime_col, dropna=False).agg(
        n_trades=("pnl", "size"),
        win_rate=("pnl", lambda s: (s > 0).mean()),
        avg_r=("r_multiple", "mean"),
        ev_dollars=("pnl", "mean"),
    ).reset_index()

    return grouped.sort_values("ev_dollars", ascending=False).reset_index(drop=True)
