"""Conditional Expected Value by Options State (extension spec §69):
"EV(alpha|GEXState)" — the options-side counterpart to
`regimes.conditional_ev.conditional_ev_by_regime` (spec §14), same
pattern exactly: join a trade sequence to the state active at each
trade's entry, aggregate EV/trade, win rate, and count per bucket.

`synced_df` is expected to come from `sync.cross_market.synchronize_frame`
(Phase J) — a futures bar frame already carrying `options_*` columns —
with a `gex_regime` column added by the caller (e.g. via
`options.features.classify_gex_regime_series` on `synced_df["options_gex"]`)
before calling this.
"""
from __future__ import annotations

import pandas as pd


def conditional_ev_by_gex_regime(
    trades_df: pd.DataFrame,
    synced_df: pd.DataFrame,
    regime_col: str = "gex_regime",
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Join each trade to the GEX regime active at its entry bar and
    aggregate. Returns one row per regime, sorted by EV/trade descending.
    """
    columns = [regime_col, "n_trades", "win_rate", "avg_r", "ev_dollars"]
    if trades_df.empty or regime_col not in synced_df.columns:
        return pd.DataFrame(columns=columns)

    merged = trades_df.merge(
        synced_df[[timestamp_col, regime_col]],
        left_on="entry_time", right_on=timestamp_col, how="left",
    )
    merged[regime_col] = merged[regime_col].fillna("UNKNOWN")

    grouped = merged.groupby(regime_col, dropna=False).agg(
        n_trades=("pnl", "size"),
        win_rate=("pnl", lambda s: (s > 0).mean()),
        avg_r=("r_multiple", "mean"),
        ev_dollars=("pnl", "mean"),
    ).reset_index()

    return grouped.sort_values("ev_dollars", ascending=False).reset_index(drop=True)
