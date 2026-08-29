import pandas as pd

from prop_alpha.data.quality import validate_ohlcv
from prop_alpha.data.synthetic import generate_synthetic_ohlcv


def test_synthetic_data_passes_quality_checks():
    df = generate_synthetic_ohlcv(n_days=20, seed=5)
    report = validate_ohlcv(df)
    assert report.is_valid, report.issues


def test_duplicate_timestamp_detected():
    df = generate_synthetic_ohlcv(n_days=5, seed=5)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    report = validate_ohlcv(df)
    assert not report.is_valid
    assert report.n_duplicate_timestamps >= 1


def test_bad_high_low_bound_detected():
    df = generate_synthetic_ohlcv(n_days=5, seed=5)
    df.loc[0, "high"] = df.loc[0, "low"] - 1.0  # high below low: invalid
    report = validate_ohlcv(df)
    assert not report.is_valid
    assert report.n_zero_range_violations >= 1
