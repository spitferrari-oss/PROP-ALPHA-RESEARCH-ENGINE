import numpy as np
import pandas as pd

from prop_alpha.statistics.dsr import compute_dsr_for_pool, deflated_sharpe_ratio, expected_max_sharpe


def test_expected_max_sharpe_zero_with_one_trial():
    assert expected_max_sharpe(np.array([1.5])) == 0.0


def test_expected_max_sharpe_increases_with_more_trials():
    rng = np.random.default_rng(0)
    small_pool = rng.normal(0, 1, size=5)
    large_pool = rng.normal(0, 1, size=200)
    small = expected_max_sharpe(small_pool)
    large = expected_max_sharpe(large_pool)
    # More independent trials -> higher expected max Sharpe under the null,
    # for a comparable spread of trial outcomes.
    assert large >= small


def test_deflated_sharpe_ratio_high_when_sharpe_far_above_benchmark():
    rng = np.random.default_rng(3)
    daily_pnl = pd.Series(rng.normal(50, 20, size=500))  # strong, stable positive edge
    result = deflated_sharpe_ratio(daily_pnl, sr_benchmark=0.0)
    assert result["dsr"] > 0.9


def test_deflated_sharpe_ratio_low_when_sharpe_below_benchmark():
    rng = np.random.default_rng(4)
    daily_pnl = pd.Series(rng.normal(0, 20, size=100))  # no edge
    result = deflated_sharpe_ratio(daily_pnl, sr_benchmark=1.0)
    assert result["dsr"] < 0.5


def test_deflated_sharpe_ratio_nan_for_degenerate_series():
    result = deflated_sharpe_ratio(pd.Series([1.0, 1.0, 1.0]), sr_benchmark=0.0)
    assert result["dsr"] != result["dsr"]  # zero std -> NaN


def test_compute_dsr_for_pool_returns_entry_per_strategy():
    rng = np.random.default_rng(5)
    pool = {
        "A": pd.Series(rng.normal(30, 20, size=200)),
        "B": pd.Series(rng.normal(-10, 20, size=200)),
        "C": pd.Series(rng.normal(5, 20, size=200)),
    }
    results = compute_dsr_for_pool(pool)
    assert set(results.keys()) == {"A", "B", "C"}
    for r in results.values():
        assert "dsr" in r and "sr_benchmark" in r
