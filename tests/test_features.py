import pandas as pd

from prop_alpha.data.synthetic import generate_synthetic_ohlcv
from prop_alpha.features.price_volume import build_feature_set


def test_feature_set_has_no_lookahead_columns_missing():
    df = generate_synthetic_ohlcv(n_days=10, seed=1)
    feats = build_feature_set(df)
    for col in ["returns", "atr_14", "vwap", "vwap_z", "delta", "cumulative_delta", "volume_z"]:
        assert col in feats.columns

    # VWAP resets each session: first bar of each day has cumulative volume
    # equal to that bar's own volume, so vwap == typical price of bar 0.
    day = feats["timestamp"].dt.tz_convert("America/New_York").dt.date
    first_bars = feats.groupby(day).head(1)
    typical = (first_bars["high"] + first_bars["low"] + first_bars["close"]) / 3
    assert (first_bars["vwap"] - typical).abs().max() < 1e-6


def test_atr_is_nonnegative():
    df = generate_synthetic_ohlcv(n_days=10, seed=2)
    feats = build_feature_set(df)
    assert (feats["atr_14"].dropna() >= 0).all()
    assert (feats["true_range"].dropna() >= 0).all()
