"""ML Meta-Alpha layer (spec §44/§45/§46/§47).

Predicts P(this alpha's next trade wins | market state) and Expected R,
not price. Follows spec §45's explicit discipline — "baseline semplice
prima, modello complesso dopo" — by always fitting a Logistic Regression
baseline alongside the Random Forest, so the complex model has to earn its
place by beating the baseline OOS (spec §45: "un modello più complesso
deve dimostrare incremento OOS"), not by assumption.

All preprocessing (imputation, scaling, one-hot encoding) is fit inside an
sklearn `Pipeline`/`ColumnTransformer` on the training call only — calling
`.fit(X_is, ...)` and later `.predict(X_oos)` never lets OOS statistics
leak into how OOS rows are transformed, the same IS-only discipline used
by the Phase 6 Gaussian Mixture regime classifier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from prop_alpha.config import MLConfig
from prop_alpha.ml.calibration import compute_calibration_metrics
from prop_alpha.ml.features import BOOL_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES


def _make_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    return ColumnTransformer([
        ("num", numeric_pipeline, NUMERIC_FEATURES + BOOL_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])


class MetaAlphaModel:
    def __init__(self, config: MLConfig | None = None, seed: int = 42):
        self.config = config or MLConfig()
        self.seed = seed
        self.baseline_pipeline: Pipeline | None = None
        self.rf_pipeline: Pipeline | None = None
        self.expected_r_pipeline: Pipeline | None = None

    def fit(self, X_is: pd.DataFrame, y_is_win: pd.Series, y_is_r: pd.Series) -> "MetaAlphaModel":
        self.baseline_pipeline = Pipeline([
            ("prep", _make_preprocessor()),
            ("clf", LogisticRegression(max_iter=1000)),
        ])
        self.baseline_pipeline.fit(X_is, y_is_win)

        self.rf_pipeline = Pipeline([
            ("prep", _make_preprocessor()),
            ("clf", RandomForestClassifier(
                n_estimators=self.config.n_estimators,
                min_samples_leaf=self.config.min_samples_leaf,
                random_state=self.seed,
            )),
        ])
        self.rf_pipeline.fit(X_is, y_is_win)

        self.expected_r_pipeline = Pipeline([
            ("prep", _make_preprocessor()),
            ("reg", RandomForestRegressor(
                n_estimators=self.config.n_estimators,
                min_samples_leaf=self.config.min_samples_leaf,
                random_state=self.seed,
            )),
        ])
        self.expected_r_pipeline.fit(X_is, y_is_r)
        return self

    def predict_proba_baseline(self, X: pd.DataFrame) -> np.ndarray:
        return self.baseline_pipeline.predict_proba(X)[:, 1]

    def predict_proba_rf(self, X: pd.DataFrame) -> np.ndarray:
        return self.rf_pipeline.predict_proba(X)[:, 1]

    def predict_expected_r(self, X: pd.DataFrame) -> np.ndarray:
        return self.expected_r_pipeline.predict(X)

    def predict_uncertainty(self, X: pd.DataFrame) -> np.ndarray:
        """Ensemble variance (spec §47): std of P(win) across the Random
        Forest's individual trees. High disagreement among trees means the
        model itself is unsure, independent of how confident its averaged
        probability looks.
        """
        prep = self.rf_pipeline.named_steps["prep"]
        clf = self.rf_pipeline.named_steps["clf"]
        X_transformed = prep.transform(X)
        tree_probs = np.stack([tree.predict_proba(X_transformed)[:, 1] for tree in clf.estimators_], axis=0)
        return tree_probs.std(axis=0)


def evaluate_meta_alpha(
    X_is: pd.DataFrame, y_is_win: pd.Series, y_is_r: pd.Series,
    X_oos: pd.DataFrame, y_oos_win: pd.Series,
    config: MLConfig | None = None, seed: int = 42,
) -> dict:
    """Fit on IS, evaluate calibration on OOS for both models, and check
    spec §45's discipline directly: did the Random Forest actually beat the
    Logistic Regression baseline OOS (lower Brier score), or should the
    simpler model be preferred?
    """
    config = config or MLConfig()
    n_oos = len(X_oos)

    if len(X_is) < config.min_samples_leaf * 4 or n_oos < config.min_oos_trades or y_is_win.nunique() < 2:
        return {"status": "INSUFFICIENT_DATA", "n_is": len(X_is), "n_oos": n_oos, "model": None}

    model = MetaAlphaModel(config, seed=seed).fit(X_is, y_is_win, y_is_r)

    baseline_proba = model.predict_proba_baseline(X_oos)
    rf_proba = model.predict_proba_rf(X_oos)
    uncertainty = model.predict_uncertainty(X_oos)

    baseline_cal = compute_calibration_metrics(y_oos_win, baseline_proba, n_bins=config.calibration_bins)
    rf_cal = compute_calibration_metrics(y_oos_win, rf_proba, n_bins=config.calibration_bins)

    rf_beats_baseline = (
        rf_cal["brier_score"] == rf_cal["brier_score"]
        and baseline_cal["brier_score"] == baseline_cal["brier_score"]
        and rf_cal["brier_score"] < baseline_cal["brier_score"]
    )

    uncertain_mask = uncertainty > config.uncertainty_threshold
    n_uncertain = int(uncertain_mask.sum())

    return {
        "status": "OK",
        "n_is": len(X_is),
        "n_oos": n_oos,
        "baseline_calibration": baseline_cal,
        "rf_calibration": rf_cal,
        "rf_beats_baseline": rf_beats_baseline,
        "recommended_model": "random_forest" if rf_beats_baseline else "logistic_regression",
        "n_oos_uncertain": n_uncertain,
        "pct_oos_uncertain": (n_uncertain / n_oos) if n_oos else float("nan"),
        "mean_uncertainty": float(np.mean(uncertainty)) if n_oos else float("nan"),
        "model": model,
    }
