import numpy as np
import pandas as pd

from prop_alpha.statistics.pbo import build_pnl_matrix, compute_pbo


def _days(n):
    return list(pd.bdate_range("2024-01-01", periods=n).date)


def test_build_pnl_matrix_fills_untraded_days_with_zero():
    days = _days(5)
    series = pd.Series([10.0, -5.0], index=[days[0], days[2]])
    matrix = build_pnl_matrix({"A": series}, days)
    assert matrix.shape == (5, 1)
    assert matrix.loc[days[1], "A"] == 0.0
    assert matrix.loc[days[0], "A"] == 10.0


def test_pbo_near_half_for_pure_noise_strategies():
    # Textbook CSCV sanity check: when every candidate is pure noise with no
    # true skill difference, being the in-sample "winner" carries no
    # information about out-of-sample rank, so it should land at the median
    # about as often as not — PBO close to 0.5, not reliably high or low.
    rng = np.random.default_rng(6)
    days = _days(160)
    pool = {f"strategy_{k}": pd.Series(rng.normal(0, 20, size=160), index=days) for k in range(10)}
    matrix = build_pnl_matrix(pool, days)
    result = compute_pbo(matrix, n_splits=8)
    assert result["n_combinations"] > 0
    assert 0.25 < result["pbo"] < 0.75


def test_pbo_low_when_one_strategy_dominates_everywhere():
    days = _days(80)
    rng = np.random.default_rng(1)
    a_vals = rng.normal(100, 5, size=80)  # consistently good everywhere
    b_vals = rng.normal(-100, 5, size=80)  # consistently bad everywhere
    matrix = build_pnl_matrix(
        {"A": pd.Series(a_vals, index=days), "B": pd.Series(b_vals, index=days)}, days
    )
    result = compute_pbo(matrix, n_splits=8)
    assert result["pbo"] < 0.5


def test_pbo_nan_with_insufficient_strategies():
    days = _days(80)
    matrix = build_pnl_matrix({"A": pd.Series(rng_vals(days))}, days)
    result = compute_pbo(matrix, n_splits=8)
    assert result["pbo"] != result["pbo"]  # NaN


def rng_vals(days):
    rng = np.random.default_rng(2)
    return pd.Series(rng.normal(0, 1, size=len(days)), index=days)
