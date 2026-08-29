"""Statistical Market Regime Engine (spec §12): Gaussian Mixture clustering
— the spec explicitly lists Gaussian Mixture alongside HMM/Markov-Switching
as an acceptable statistical regime model, so this is the "or" branch of
"rule-based; HMM; clustering; change point" that doesn't require pulling in
a separate HMM dependency.

Critically, the model is `fit` on in-sample days only and then `predict`ed
on the full series — fitting on the whole dataset (OOS included) would let
information about OOS market structure leak into the cluster definitions
every OOS backtest then gets evaluated against, which is exactly the kind
of look-ahead spec §28 (Data Leakage Engine) exists to catch.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

from prop_alpha.config import RegimeConfig

FEATURE_COLUMNS = ["log_returns", "realized_vol_20", "volume_z"]


class GmmRegimeClassifier:
    def __init__(self, config: RegimeConfig | None = None):
        self.config = config or RegimeConfig()
        self.model: GaussianMixture | None = None
        self.feature_mean: pd.Series | None = None
        self.feature_std: pd.Series | None = None

    def fit(self, df_in_sample: pd.DataFrame) -> "GmmRegimeClassifier":
        missing = [c for c in FEATURE_COLUMNS if c not in df_in_sample.columns]
        if missing:
            raise ValueError(f"GmmRegimeClassifier.fit requires columns {missing}")

        X = df_in_sample[FEATURE_COLUMNS].dropna()
        if len(X) < self.config.gmm_n_components * 5:
            raise ValueError(
                f"Not enough in-sample rows ({len(X)}) to fit a {self.config.gmm_n_components}-component GMM"
            )

        self.feature_mean = X.mean()
        self.feature_std = X.std().replace(0, 1.0)
        X_scaled = (X - self.feature_mean) / self.feature_std

        self.model = GaussianMixture(
            n_components=self.config.gmm_n_components,
            random_state=self.config.gmm_seed,
            n_init=3,
        )
        self.model.fit(X_scaled.to_numpy())
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("GmmRegimeClassifier.predict called before fit")

        df = df.copy()
        valid = df[FEATURE_COLUMNS].notna().all(axis=1)
        labels = np.full(len(df), -1, dtype=int)
        confidence = np.full(len(df), np.nan)

        if valid.any():
            X = df.loc[valid, FEATURE_COLUMNS]
            X_scaled = (X - self.feature_mean) / self.feature_std
            proba = self.model.predict_proba(X_scaled.to_numpy())
            labels[valid.to_numpy()] = proba.argmax(axis=1)
            confidence[valid.to_numpy()] = proba.max(axis=1)

        df["regime_gmm"] = labels
        df["regime_gmm_confidence"] = confidence
        return df
