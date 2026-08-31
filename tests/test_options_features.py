import numpy as np
import pandas as pd
import pytest

from prop_alpha.options.features import (
    GexRegime,
    GexRegimeThresholds,
    classify_gex_regime,
    classify_gex_regime_series,
    compute_dex_state,
    compute_gex_dynamics,
    normalize_gex_series,
)


def test_normalize_gex_series_zscore():
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    normalized = normalize_gex_series(values)
    assert normalized.mean() == pytest.approx(0.0, abs=1e-9)
    assert normalized.std() == pytest.approx(1.0, abs=1e-9)


def test_normalize_gex_series_too_few_observations_is_nan():
    result = normalize_gex_series(pd.Series([1.0]))
    assert result.isna().all()


def test_normalize_gex_series_zero_variance_is_nan():
    result = normalize_gex_series(pd.Series([5.0, 5.0, 5.0]))
    assert result.isna().all()


def test_classify_gex_regime_thresholds():
    thresholds = GexRegimeThresholds()
    assert classify_gex_regime(3.0, thresholds) == GexRegime.STRONG_POSITIVE_GAMMA
    assert classify_gex_regime(1.0, thresholds) == GexRegime.POSITIVE_GAMMA
    assert classify_gex_regime(0.0, thresholds) == GexRegime.NEUTRAL
    assert classify_gex_regime(-1.0, thresholds) == GexRegime.NEGATIVE_GAMMA
    assert classify_gex_regime(-3.0, thresholds) == GexRegime.STRONG_NEGATIVE_GAMMA


def test_classify_gex_regime_none_or_nan_is_unknown():
    assert classify_gex_regime(None) == GexRegime.UNKNOWN
    assert classify_gex_regime(float("nan")) == GexRegime.UNKNOWN


def test_classify_gex_regime_series_combines_normalize_and_classify():
    # Mostly-zero series with two extreme outliers -> the outliers land
    # well past +-2 std, the zeros stay within the neutral band.
    values = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -20.0, 20.0])
    labels = classify_gex_regime_series(values)
    assert labels.iloc[-2] == GexRegime.STRONG_NEGATIVE_GAMMA.value
    assert labels.iloc[-1] == GexRegime.STRONG_POSITIVE_GAMMA.value
    assert labels.iloc[0] == GexRegime.NEUTRAL.value


def test_compute_dex_state_magnitude_and_sign():
    dex = pd.Series([10.0, -5.0, 0.0, np.nan])
    result = compute_dex_state(dex)
    assert list(result["dex_magnitude"].iloc[:3]) == [10.0, 5.0, 0.0]
    assert np.isnan(result["dex_magnitude"].iloc[3])
    assert result["dex_sign"].iloc[0] == 1.0
    assert result["dex_sign"].iloc[1] == -1.0
    assert result["dex_sign"].iloc[2] == 0.0
    assert np.isnan(result["dex_sign"].iloc[3])


def test_compute_dex_state_concentration_is_always_nan():
    dex = pd.Series([1.0, 2.0])
    result = compute_dex_state(dex)
    assert result["dex_concentration"].isna().all()


def test_compute_dex_state_change_and_acceleration():
    dex = pd.Series([1.0, 3.0, 6.0, 10.0])
    result = compute_dex_state(dex)
    assert list(result["dex_change"].dropna()) == [2.0, 3.0, 4.0]
    assert list(result["dex_acceleration"].dropna()) == [1.0, 1.0]


def test_compute_gex_dynamics_delta_and_delta2():
    gex = pd.Series([100.0, 110.0, 125.0, 130.0])
    result = compute_gex_dynamics(gex)
    assert list(result["gex_delta"].dropna()) == [10.0, 15.0, 5.0]
    assert list(result["gex_delta2"].dropna()) == [5.0, -10.0]
