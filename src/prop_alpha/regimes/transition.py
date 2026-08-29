"""Regime Transition Engine (spec §13): not just "what regime is this?" but
"is the regime changing?" — a bar is flagged `regime_transitioning` when
either (a) the rule-based label has flipped repeatedly in the last few
bars (an unstable, whipsawing classification) or (b) the statistical
classifier's own posterior confidence in its top cluster is weak (the GMM
itself is unsure which regime this bar belongs to). Both signals only look
backward/at the current bar, so there is no look-ahead.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.config import RegimeConfig


def compute_transition_flags(
    df: pd.DataFrame,
    config: RegimeConfig | None = None,
    regime_col: str = "regime_rule",
    confidence_col: str = "regime_gmm_confidence",
) -> pd.DataFrame:
    config = config or RegimeConfig()
    df = df.copy()

    if regime_col in df.columns:
        changed = df[regime_col] != df[regime_col].shift(1)
        flip_count = changed.rolling(config.transition_lookback_bars).sum()
        unstable_label = flip_count >= 2
    else:
        unstable_label = pd.Series(False, index=df.index)

    if confidence_col in df.columns:
        low_confidence = df[confidence_col] < config.transition_confidence_threshold
    else:
        low_confidence = pd.Series(False, index=df.index)

    df["regime_transitioning"] = unstable_label.fillna(False) | low_confidence.fillna(False)
    return df
