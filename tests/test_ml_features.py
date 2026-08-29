import pandas as pd

from prop_alpha.ml.features import ALL_FEATURES, build_ml_feature_matrix


def _trades():
    ts = pd.date_range("2024-01-02 09:30", periods=3, freq="15min", tz="America/New_York")
    return pd.DataFrame({
        "entry_time": ts,
        "exit_time": ts,
        "r_multiple": [1.5, -1.0, 2.0],
        "pnl": [150.0, -100.0, 200.0],
    })


def _features():
    ts = pd.date_range("2024-01-02 09:30", periods=3, freq="15min", tz="America/New_York")
    return pd.DataFrame({
        "timestamp": ts,
        "volatility_percentile": [0.5, 0.6, 0.7],
        "relative_volume": [1.0, 1.2, 0.8],
        "vwap_z": [0.1, -0.2, 0.3],
        "delta_acceleration_z": [0.0, 1.0, -1.0],
        "minutes_since_session_open": [15.0, 30.0, 45.0],
        "atr_14": [10.0, 11.0, 12.0],
        "high_liquidity": [True, False, True],
        "low_liquidity": [False, True, False],
        "regime_transitioning": [False, False, True],
        "regime_rule": ["TREND_UP", "RANGE", "BREAKOUT"],
        "session": ["US_OPEN", "US_OPEN", "US_LUNCH"],
    })


def test_columns_and_shapes():
    X, y_win, y_r = build_ml_feature_matrix(_trades(), _features())
    assert list(X.columns) == ALL_FEATURES
    assert len(X) == len(y_win) == len(y_r) == 3


def test_labels_correct():
    _, y_win, y_r = build_ml_feature_matrix(_trades(), _features())
    assert y_win.tolist() == [1, 0, 1]
    assert y_r.tolist() == [1.5, -1.0, 2.0]


def test_bool_features_cast_to_float():
    X, _, _ = build_ml_feature_matrix(_trades(), _features())
    assert X["high_liquidity"].tolist() == [1.0, 0.0, 1.0]


def test_categorical_features_kept_as_strings():
    X, _, _ = build_ml_feature_matrix(_trades(), _features())
    assert X["regime_rule"].tolist() == ["TREND_UP", "RANGE", "BREAKOUT"]


def test_missing_feature_columns_become_nan():
    feats = _features().drop(columns=["vwap_z"])
    X, _, _ = build_ml_feature_matrix(_trades(), feats)
    assert X["vwap_z"].isna().all()


def test_empty_trades_returns_empty_frame():
    empty = _trades().iloc[0:0]
    X, y_win, y_r = build_ml_feature_matrix(empty, _features())
    assert X.empty
    assert list(X.columns) == ALL_FEATURES
    assert len(y_win) == 0 and len(y_r) == 0
