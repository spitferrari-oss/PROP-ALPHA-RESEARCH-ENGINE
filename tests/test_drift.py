import numpy as np
import pandas as pd

from prop_alpha.paper.drift import compute_feature_drift, compute_psi


def test_compute_psi_zero_for_identical_distributions():
    rng = np.random.default_rng(0)
    data = rng.normal(0, 1, 500)
    psi = compute_psi(data, data)
    assert psi < 1e-6


def test_compute_psi_large_for_shifted_distribution():
    rng = np.random.default_rng(1)
    expected = rng.normal(0, 1, 500)
    actual = rng.normal(5, 1, 500)
    psi = compute_psi(expected, actual)
    assert psi > 0.2


def test_compute_psi_nan_when_insufficient_expected_data():
    psi = compute_psi(np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0]), n_bins=10)
    assert psi != psi


def test_compute_feature_drift_flags_drifted_features_only():
    rng = np.random.default_rng(2)
    df_is = pd.DataFrame({
        "volatility_percentile": rng.uniform(0, 1, 300),
        "relative_volume": rng.uniform(0.5, 1.5, 300),
    })
    df_shadow = pd.DataFrame({
        "volatility_percentile": rng.normal(5, 0.1, 100),  # far outside the IS distribution
        "relative_volume": rng.uniform(0.5, 1.5, 100),     # same distribution as IS
    })
    findings = compute_feature_drift(
        df_is, df_shadow, feature_columns=["volatility_percentile", "relative_volume"],
    )
    by_feature = {f["feature"]: f for f in findings}
    assert by_feature["volatility_percentile"]["drifted"] is True
    assert by_feature["relative_volume"]["drifted"] is False


def test_compute_feature_drift_skips_missing_columns():
    df_is = pd.DataFrame({"a": [1, 2, 3]})
    df_shadow = pd.DataFrame({"a": [1, 2, 3]})
    findings = compute_feature_drift(df_is, df_shadow, feature_columns=["a", "missing_col"])
    assert len(findings) == 1
    assert findings[0]["feature"] == "a"
