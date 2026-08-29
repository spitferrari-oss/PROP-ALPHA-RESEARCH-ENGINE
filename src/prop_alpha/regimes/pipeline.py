"""Regime Engine orchestration: rule-based classification (bar-by-bar, no
fitting needed) + Gaussian Mixture classification (fit on in-sample days
only) + transition flags, chained into one call.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.config import RegimeConfig
from prop_alpha.regimes.rule_based import classify_regime_rule_based
from prop_alpha.regimes.statistical import GmmRegimeClassifier
from prop_alpha.regimes.transition import compute_transition_flags


def build_regime_features(
    df_feat: pd.DataFrame,
    in_sample_days: set,
    config: RegimeConfig | None = None,
    timezone: str = "America/New_York",
) -> pd.DataFrame:
    config = config or RegimeConfig()

    df = classify_regime_rule_based(df_feat, config)

    day = df["timestamp"].dt.tz_convert(timezone).dt.date
    df_in_sample = df[day.isin(in_sample_days)]
    try:
        gmm = GmmRegimeClassifier(config).fit(df_in_sample)
        df = gmm.predict(df)
    except ValueError:
        # Not enough in-sample data to fit a GMM (e.g. a very short demo
        # run) — fall back to rule-based-only regime features rather than
        # failing the whole pipeline.
        df["regime_gmm"] = -1
        df["regime_gmm_confidence"] = float("nan")

    df = compute_transition_flags(df, config)
    return df
