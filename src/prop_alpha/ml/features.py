"""ML Meta-Alpha feature matrix (spec §44): the market-state features a
meta-model conditions on to predict "will this alpha's next trade work" —
regime, volatility, liquidity, session, order flow — joined to each trade
at its own entry bar, so nothing here can see anything past the moment the
trade was taken.
"""
from __future__ import annotations

import pandas as pd

NUMERIC_FEATURES = [
    "volatility_percentile", "relative_volume", "vwap_z",
    "delta_acceleration_z", "minutes_since_session_open", "atr_14",
]
BOOL_FEATURES = ["high_liquidity", "low_liquidity", "regime_transitioning"]
CATEGORICAL_FEATURES = ["regime_rule", "session"]
ALL_FEATURES = NUMERIC_FEATURES + BOOL_FEATURES + CATEGORICAL_FEATURES


def build_ml_feature_matrix(trades_df: pd.DataFrame, df_feat: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Returns (X, y_win, y_r) aligned on the same index. `y_win` is 1 for a
    profitable trade, `y_r` is the trade's realized R-multiple (a
    regression target for Expected R, spec §46).
    """
    if trades_df.empty:
        return pd.DataFrame(columns=ALL_FEATURES), pd.Series(dtype=int), pd.Series(dtype=float)

    available = [c for c in ALL_FEATURES if c in df_feat.columns]
    merged = trades_df.merge(
        df_feat[["timestamp", *available]],
        left_on="entry_time", right_on="timestamp", how="left",
    ).reset_index(drop=True)

    X = merged.reindex(columns=ALL_FEATURES)
    for col in BOOL_FEATURES:
        X[col] = X[col].astype(float)
    for col in NUMERIC_FEATURES:
        X[col] = pd.to_numeric(X[col], errors="coerce")

    y_win = (merged["pnl"] > 0).astype(int)
    y_r = merged["r_multiple"].astype(float)
    return X, y_win, y_r
