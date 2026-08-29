import numpy as np

from prop_alpha.ml.calibration import compute_calibration_metrics


def test_well_calibrated_probabilities_have_low_brier_and_ece():
    rng = np.random.default_rng(0)
    n = 2000
    y_prob = rng.uniform(0, 1, n)
    y_true = (rng.uniform(0, 1, n) < y_prob).astype(int)  # outcomes literally match stated probabilities
    result = compute_calibration_metrics(y_true, y_prob, n_bins=10)
    assert result["brier_score"] < 0.3
    assert result["ece"] < 0.1


def test_badly_calibrated_probabilities_have_high_ece():
    rng = np.random.default_rng(1)
    n = 500
    # Model always predicts ~0.9 confidence, but true outcome is 50/50 -> badly overconfident.
    y_prob = np.full(n, 0.9)
    y_true = (rng.uniform(0, 1, n) < 0.5).astype(int)
    result = compute_calibration_metrics(y_true, y_prob, n_bins=5)
    assert result["ece"] > 0.3


def test_single_class_returns_nan():
    y_true = np.zeros(50)
    y_prob = np.full(50, 0.3)
    result = compute_calibration_metrics(y_true, y_prob)
    assert result["brier_score"] != result["brier_score"]  # NaN


def test_too_few_observations_returns_nan():
    result = compute_calibration_metrics([0, 1], [0.4, 0.6], n_bins=10)
    assert result["brier_score"] != result["brier_score"]


def test_n_obs_always_reported():
    result = compute_calibration_metrics(np.zeros(50), np.full(50, 0.5))
    assert result["n_obs"] == 50
