import numpy as np
import pandas as pd

from prop_alpha.config import MLConfig
from prop_alpha.ml.meta_alpha import MetaAlphaModel, evaluate_meta_alpha


def _synthetic_dataset(n=400, seed=0):
    rng = np.random.default_rng(seed)
    regime = rng.choice(["TREND_UP", "RANGE", "BREAKOUT"], size=n)
    session = rng.choice(["US_OPEN", "US_LUNCH"], size=n)
    vol_pct = rng.uniform(0, 1, n)
    rel_vol = rng.uniform(0.3, 2.0, n)
    vwap_z = rng.normal(0, 1, n)
    delta_z = rng.normal(0, 1, n)
    minutes = rng.uniform(0, 120, n)
    atr = rng.uniform(5, 20, n)
    high_liq = rng.random(n) < 0.3
    low_liq = rng.random(n) < 0.3
    transitioning = rng.random(n) < 0.2

    # True signal: TREND_UP regime strongly predicts a win; everything else is noise.
    p_win = np.where(regime == "TREND_UP", 0.85, 0.45)
    y_win = (rng.uniform(0, 1, n) < p_win).astype(int)
    y_r = np.where(y_win == 1, rng.uniform(0.5, 3.0, n), rng.uniform(-2.0, -0.2, n))

    X = pd.DataFrame({
        "volatility_percentile": vol_pct, "relative_volume": rel_vol, "vwap_z": vwap_z,
        "delta_acceleration_z": delta_z, "minutes_since_session_open": minutes, "atr_14": atr,
        "high_liquidity": high_liq.astype(float), "low_liquidity": low_liq.astype(float),
        "regime_transitioning": transitioning.astype(float),
        "regime_rule": regime, "session": session,
    })
    return X, pd.Series(y_win), pd.Series(y_r)


def test_fit_and_predict_shapes():
    X, y_win, y_r = _synthetic_dataset(n=300, seed=1)
    model = MetaAlphaModel(MLConfig(n_estimators=50), seed=1).fit(X, y_win, y_r)

    X_oos, _, _ = _synthetic_dataset(n=50, seed=2)
    proba_base = model.predict_proba_baseline(X_oos)
    proba_rf = model.predict_proba_rf(X_oos)
    expected_r = model.predict_expected_r(X_oos)
    uncertainty = model.predict_uncertainty(X_oos)

    assert len(proba_base) == len(proba_rf) == len(expected_r) == len(uncertainty) == 50
    assert ((proba_base >= 0) & (proba_base <= 1)).all()
    assert ((proba_rf >= 0) & (proba_rf <= 1)).all()
    assert (uncertainty >= 0).all()


def test_model_learns_the_real_regime_signal():
    X, y_win, y_r = _synthetic_dataset(n=800, seed=3)
    model = MetaAlphaModel(MLConfig(n_estimators=100), seed=3).fit(X, y_win, y_r)

    trend_up_row = X.iloc[[0]].copy()
    trend_up_row.loc[:, "regime_rule"] = "TREND_UP"
    range_row = X.iloc[[0]].copy()
    range_row.loc[:, "regime_rule"] = "RANGE"

    p_trend = model.predict_proba_rf(trend_up_row)[0]
    p_range = model.predict_proba_rf(range_row)[0]
    assert p_trend > p_range


def test_evaluate_meta_alpha_insufficient_data():
    X, y_win, y_r = _synthetic_dataset(n=10, seed=4)
    result = evaluate_meta_alpha(X, y_win, y_r, X.iloc[:5], y_win.iloc[:5], config=MLConfig(min_oos_trades=15))
    assert result["status"] == "INSUFFICIENT_DATA"


def test_evaluate_meta_alpha_returns_calibration_and_recommendation():
    X_is, y_is_win, y_is_r = _synthetic_dataset(n=600, seed=5)
    X_oos, y_oos_win, _ = _synthetic_dataset(n=150, seed=6)
    result = evaluate_meta_alpha(X_is, y_is_win, y_is_r, X_oos, y_oos_win, config=MLConfig(n_estimators=50))
    assert result["status"] == "OK"
    assert "baseline_calibration" in result and "rf_calibration" in result
    assert result["recommended_model"] in ("random_forest", "logistic_regression")
    assert 0 <= result["pct_oos_uncertain"] <= 1


def test_evaluate_meta_alpha_single_class_is_insufficient():
    X, _, y_r = _synthetic_dataset(n=100, seed=7)
    y_win_all_ones = pd.Series(np.ones(100, dtype=int))
    result = evaluate_meta_alpha(X, y_win_all_ones, y_r, X.iloc[:30], y_win_all_ones.iloc[:30],
                                  config=MLConfig(min_oos_trades=15))
    assert result["status"] == "INSUFFICIENT_DATA"
