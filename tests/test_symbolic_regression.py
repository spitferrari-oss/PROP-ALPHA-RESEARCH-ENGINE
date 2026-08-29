import math

import numpy as np
import pandas as pd

from prop_alpha.discovery.symbolic_regression import compute_forward_return, symbolic_search


def test_compute_forward_return_shifts_forward():
    df = pd.DataFrame({"close": [100.0, 110.0, 121.0, 100.0]})
    fwd = compute_forward_return(df, horizon_bars=1)
    # fwd[0] should be the return from bar 0 to bar 1: 110/100 - 1 = 0.10
    assert math.isclose(fwd.iloc[0], 0.10, abs_tol=1e-9)
    assert math.isclose(fwd.iloc[1], 0.10, abs_tol=1e-9)
    assert pd.isna(fwd.iloc[-1])  # no future bar to look at


def test_symbolic_search_finds_strong_single_feature_correlate():
    rng = np.random.default_rng(0)
    n = 500
    feature_a = rng.normal(0, 1, n)
    noise = rng.normal(0, 5, n)
    target = pd.Series(feature_a * 10 + noise)  # target is mostly driven by feature_a
    df = pd.DataFrame({
        "feature_a": feature_a,
        "feature_b": rng.normal(0, 1, n),  # pure noise, uncorrelated
    })
    results = symbolic_search(df, ["feature_a", "feature_b"], target, top_k=5, min_obs=100)
    assert results[0]["expression"] == "feature_a"
    assert abs(results[0]["ic"]) > 0.5


def test_symbolic_search_prefers_lower_complexity_at_similar_ic():
    rng = np.random.default_rng(1)
    n = 500
    feature_a = rng.normal(0, 1, n)
    feature_b = rng.normal(0, 1, n)
    target = pd.Series(feature_a * 10 + rng.normal(0, 0.1, n))  # near-perfect single-feature fit
    df = pd.DataFrame({"feature_a": feature_a, "feature_b": feature_b})
    results = symbolic_search(df, ["feature_a", "feature_b"], target, top_k=10, min_obs=100)
    # The best result should be the single-feature (complexity=1) expression,
    # not a combo, since it already captures almost all the signal.
    assert results[0]["complexity"] == 1


def test_min_obs_filters_out_sparse_expressions():
    df = pd.DataFrame({"feature_a": [1.0, 2.0, np.nan, np.nan, np.nan]})
    target = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    results = symbolic_search(df, ["feature_a"], target, top_k=5, min_obs=3)
    assert results == []


def test_results_capped_at_top_k():
    rng = np.random.default_rng(2)
    n = 300
    df = pd.DataFrame({f"f{i}": rng.normal(0, 1, n) for i in range(5)})
    target = pd.Series(rng.normal(0, 1, n))
    results = symbolic_search(df, list(df.columns), target, top_k=3, min_obs=50)
    assert len(results) <= 3
