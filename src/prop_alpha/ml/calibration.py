"""Probability calibration diagnostics (spec §101): a model that says "70%"
should be right about 70% of the time in that bucket. Brier score and log
loss summarize overall probabilistic accuracy; Expected Calibration Error
(ECE) summarizes the reliability-curve gap directly.
"""
from __future__ import annotations

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss


def compute_calibration_metrics(y_true, y_prob, n_bins: int = 10) -> dict:
    y_true = np.asarray(y_true)
    y_prob = np.clip(np.asarray(y_prob, dtype=float), 1e-6, 1 - 1e-6)
    n_obs = len(y_true)

    if n_obs < max(n_bins, 2) or len(np.unique(y_true)) < 2:
        return {"brier_score": float("nan"), "log_loss": float("nan"), "ece": float("nan"), "n_obs": n_obs}

    brier = float(brier_score_loss(y_true, y_prob))
    ll = float(log_loss(y_true, y_prob, labels=[0, 1]))

    n_bins_used = min(n_bins, n_obs)
    frac_pos, mean_pred = calibration_curve(y_true, y_prob, n_bins=n_bins_used, strategy="quantile")
    ece = float(np.mean(np.abs(frac_pos - mean_pred))) if len(frac_pos) else float("nan")

    return {"brier_score": brier, "log_loss": ll, "ece": ece, "n_obs": n_obs}
