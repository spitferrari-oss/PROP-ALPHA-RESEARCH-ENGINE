"""Drift Detection (spec §99): Population Stability Index between the
in-sample feature distribution an alpha/model was built on and the
shadow-period distribution, for a handful of key market-state features.

Only feature drift via PSI is implemented here. spec §99 also names regime
drift, performance drift, volatility/liquidity drift, execution drift, and
complementary statistical tests (KS, Jensen-Shannon divergence, Wasserstein
distance, change-point detection) — none of those are built yet; this is a
documented gap, not a claim of full coverage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PSI_DRIFT_THRESHOLD = 0.2
DEFAULT_DRIFT_FEATURES = ["volatility_percentile", "relative_volume", "vwap_z"]


def compute_psi(expected: np.ndarray, actual: np.ndarray, n_bins: int = 10) -> float:
    """Population Stability Index: bins are drawn from `expected`'s own
    quantiles, so a PSI of 0 means `actual` reproduces `expected`'s
    distribution exactly; PSI > 0.2 is the conventional "significant
    drift" threshold.
    """
    expected = np.asarray(expected, dtype=float)
    expected = expected[~np.isnan(expected)]
    actual = np.asarray(actual, dtype=float)
    actual = actual[~np.isnan(actual)]

    if len(expected) < n_bins or len(actual) == 0:
        return float("nan")

    quantiles = np.linspace(0, 1, n_bins + 1)
    edges = np.unique(np.quantile(expected, quantiles))
    if len(edges) < 3:
        return float("nan")
    edges[0], edges[-1] = -np.inf, np.inf

    expected_counts, _ = np.histogram(expected, bins=edges)
    actual_counts, _ = np.histogram(actual, bins=edges)

    expected_pct = np.clip(expected_counts / expected_counts.sum(), 1e-4, None)
    actual_pct = np.clip(actual_counts / actual_counts.sum(), 1e-4, None)

    return float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))


def compute_feature_drift(
    df_is: pd.DataFrame,
    df_shadow: pd.DataFrame,
    feature_columns: list[str] | None = None,
    psi_threshold: float = PSI_DRIFT_THRESHOLD,
) -> list[dict]:
    """`df_is`/`df_shadow` need only carry the columns in `feature_columns` —
    in practice the IS/OOS ML feature matrices already built for the Meta-
    Alpha layer (`ml.features.build_ml_feature_matrix`) are passed directly,
    so no separate feature extraction pass is needed.
    """
    feature_columns = feature_columns or DEFAULT_DRIFT_FEATURES
    findings = []
    for col in feature_columns:
        if col not in df_is.columns or col not in df_shadow.columns:
            continue
        psi = compute_psi(df_is[col].to_numpy(), df_shadow[col].to_numpy())
        findings.append({
            "feature": col,
            "psi": psi,
            "drifted": psi == psi and psi > psi_threshold,
        })
    return findings
