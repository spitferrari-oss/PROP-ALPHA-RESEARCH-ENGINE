import pandas as pd
import pytest

from prop_alpha.data.normalize import TRADE_COLUMNS, normalize_frame
from prop_alpha.data.schema import OPTIONAL_COLUMNS, REQUIRED_COLUMNS


def _ts(n=3):
    return pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")


def test_normalize_frame_requires_timestamp_column():
    df = pd.DataFrame({"open": [1.0]})
    with pytest.raises(ValueError, match="'timestamp' column not found"):
        normalize_frame(df, "ohlcv-1m")


def test_normalize_frame_requires_datetime_timestamp_column():
    df = pd.DataFrame({"timestamp": ["2024-01-01", "2024-01-02"]})
    with pytest.raises(ValueError, match="must already be a datetime column"):
        normalize_frame(df, "ohlcv-1m")


def test_normalize_frame_requires_tz_aware_timestamp():
    df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=2)})  # naive
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_frame(df, "ohlcv-1m")


def test_normalize_bars_aliases_onto_canonical_schema():
    df = pd.DataFrame({
        "timestamp": _ts(), "open": [1.0, 2.0, 3.0], "high": [1.1, 2.1, 3.1],
        "low": [0.9, 1.9, 2.9], "close": [1.05, 2.05, 3.05], "volume": [10, 20, 30],
        "symbol": ["NQZ4"] * 3,
    })
    out = normalize_frame(df, "ohlcv-1m")
    assert list(out.columns) == REQUIRED_COLUMNS + OPTIONAL_COLUMNS
    assert out["buy_volume"].isna().all()


def test_normalize_bars_missing_column_raises():
    df = pd.DataFrame({"timestamp": _ts(1), "open": [1.0], "high": [1.1], "low": [0.9]})
    with pytest.raises(ValueError, match="missing expected column"):
        normalize_frame(df, "ohlcv-1m")


def test_normalize_trades_aliases_onto_canonical_schema():
    df = pd.DataFrame({
        "timestamp": _ts(), "price": [100.0, 100.5, 101.0], "size": [1, 2, 3],
        "side": ["A", "B", "A"], "flags": [0, 0, 130],
    })
    out = normalize_frame(df, "trades")
    assert list(out.columns[:4]) == TRADE_COLUMNS
    assert "flags" in out.columns  # extra native columns preserved


def test_normalize_trades_fills_missing_side_with_none():
    df = pd.DataFrame({"timestamp": _ts(2), "price": [1.0, 2.0], "size": [1, 1]})
    out = normalize_frame(df, "trades")
    assert out["side"].isna().all()


def test_normalize_trades_missing_column_raises():
    df = pd.DataFrame({"timestamp": _ts(1), "price": [1.0]})  # no size
    with pytest.raises(ValueError, match="missing expected column"):
        normalize_frame(df, "trades")


def test_normalize_book_schema_keeps_native_columns_untouched():
    df = pd.DataFrame({
        "timestamp": _ts(2), "bid_px_00": [100.0, 100.5], "ask_px_00": [100.25, 100.75],
    })
    out = normalize_frame(df, "mbp-10")
    assert list(out.columns) == list(df.columns)
    pd.testing.assert_frame_equal(out, df)
