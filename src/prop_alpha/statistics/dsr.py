"""Deflated Sharpe Ratio (spec §30; Bailey & Lopez de Prado 2014).

A raw Sharpe ratio doesn't know how many strategies were tried to find it.
DSR asks: given N independent trials, what Sharpe would the *best* of them
reach by pure luck? Then it reports the probability that a candidate's
actual Sharpe exceeds that luck-adjusted benchmark, accounting for the
estimate's own skew/kurtosis and sample length. A DSR near 1.0 means the
Sharpe is unlikely to be a multiple-testing artifact; a low DSR means it
plausibly is, even if the raw Sharpe looks good.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe(trial_sharpe_ratios: np.ndarray) -> float:
    """Expected maximum Sharpe ratio across N independent trials under the
    null of zero true skill, using the variance of the observed trial
    Sharpe ratios as the estimate of each trial's sampling variance.
    """
    n = len(trial_sharpe_ratios)
    if n < 2:
        return 0.0
    sigma_sr = float(np.std(trial_sharpe_ratios, ddof=1))
    if sigma_sr == 0:
        return 0.0
    return sigma_sr * (
        (1 - EULER_MASCHERONI) * norm.ppf(1 - 1.0 / n)
        + EULER_MASCHERONI * norm.ppf(1 - 1.0 / (n * np.e))
    )


def deflated_sharpe_ratio(daily_pnl: pd.Series, sr_benchmark: float) -> dict:
    """DSR for one strategy's daily P&L against a benchmark Sharpe (typically
    `expected_max_sharpe` over the trial pool). All Sharpe figures here are
    per-*period* (daily), matching the `n_obs` used in the formula.
    """
    s = daily_pnl.dropna()
    n = len(s)
    if n < 3 or s.std() == 0:
        return {"sharpe_daily": 0.0, "dsr": float("nan"), "n_obs": n}

    sharpe_hat = float(s.mean() / s.std())
    skew = float(s.skew()) if n > 2 else 0.0
    # pandas .kurtosis() is excess kurtosis (normal=0); the PSR/DSR formula
    # wants raw (Pearson) kurtosis, where normal=3.
    kurt = float(s.kurtosis()) + 3.0 if n > 3 else 3.0

    denom = np.sqrt(max(1 - skew * sharpe_hat + (kurt - 1) / 4 * sharpe_hat**2, 1e-12))
    z = (sharpe_hat - sr_benchmark) * np.sqrt(n - 1) / denom
    return {"sharpe_daily": sharpe_hat, "dsr": float(norm.cdf(z)), "n_obs": n}


def compute_dsr_for_pool(daily_pnl_by_strategy: dict[str, pd.Series]) -> dict[str, dict]:
    """Compute DSR for every strategy in the pool against the pool's own
    expected-max-Sharpe-under-the-null benchmark (spec §30/§134).
    """
    sharpe_by_name = {}
    for name, series in daily_pnl_by_strategy.items():
        s = series.dropna()
        sharpe_by_name[name] = float(s.mean() / s.std()) if len(s) > 2 and s.std() > 0 else 0.0

    sr_benchmark = expected_max_sharpe(np.array(list(sharpe_by_name.values())))
    return {
        name: {**deflated_sharpe_ratio(daily_pnl_by_strategy[name], sr_benchmark), "sr_benchmark": sr_benchmark}
        for name in daily_pnl_by_strategy
    }
