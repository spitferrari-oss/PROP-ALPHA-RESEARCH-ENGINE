import numpy as np
import pandas as pd

from prop_alpha.config import RegimeConfig
from prop_alpha.regimes.rule_based import classify_regime_rule_based


def _base_row(**overrides):
    row = dict(
        volatility_percentile=0.5, atr_14=10.0, true_range=10.0, relative_volume=1.0,
        close=100.0, vwap=100.0, vwap_slope=0.0, prior_swing_high=110.0, prior_swing_low=90.0,
        rolling_high_20=105.0, rolling_low_20=95.0,
    )
    row.update(overrides)
    return row


def _df_from_rows(rows: list[dict]) -> pd.DataFrame:
    ts = pd.date_range("2024-01-02 09:30", periods=len(rows), freq="15min", tz="America/New_York")
    df = pd.DataFrame(rows)
    df.insert(0, "timestamp", ts)
    return df


def test_panic_detected():
    rows = [_base_row(true_range=50.0, atr_14=10.0, relative_volume=5.0)]
    out = classify_regime_rule_based(_df_from_rows(rows))
    assert out["regime_rule"].iloc[0] == "PANIC"


def test_breakout_detected():
    rows = [_base_row(close=115.0, prior_swing_high=110.0, volatility_percentile=0.7)]
    out = classify_regime_rule_based(_df_from_rows(rows))
    assert out["regime_rule"].iloc[0] == "BREAKOUT"


def test_compression_detected():
    rows = [_base_row(volatility_percentile=0.1, true_range=2.0, atr_14=10.0)]
    out = classify_regime_rule_based(_df_from_rows(rows))
    assert out["regime_rule"].iloc[0] == "COMPRESSION"


def test_expansion_detected():
    rows = [_base_row(true_range=20.0, atr_14=10.0, volatility_percentile=0.5)]
    out = classify_regime_rule_based(_df_from_rows(rows))
    assert out["regime_rule"].iloc[0] == "EXPANSION"


def test_trend_up_detected():
    # Needs 6 rows so rolling_high_20.shift(5) is defined (trend_lookback_bars=5 default).
    rows = [_base_row(rolling_high_20=95.0 + i) for i in range(6)]
    rows[-1].update(close=120.0, vwap=100.0, vwap_slope=1.0, true_range=5.0, atr_14=10.0,
                     volatility_percentile=0.3)
    out = classify_regime_rule_based(_df_from_rows(rows))
    assert out["regime_rule"].iloc[-1] == "TREND_UP"


def test_high_and_low_volatility_fallback():
    high = _df_from_rows([_base_row(volatility_percentile=0.95, true_range=5.0, atr_14=10.0)])
    # true_range must clear compression's tr < 0.6*atr bar (=6.0) too, or the
    # higher-priority COMPRESSION rule would win instead of LOW_VOLATILITY.
    low = _df_from_rows([_base_row(volatility_percentile=0.05, true_range=8.0, atr_14=10.0)])
    assert classify_regime_rule_based(high)["regime_rule"].iloc[0] == "HIGH_VOLATILITY"
    assert classify_regime_rule_based(low)["regime_rule"].iloc[0] == "LOW_VOLATILITY"


def test_range_default_when_nothing_else_matches():
    rows = [_base_row(volatility_percentile=0.5, true_range=5.0, atr_14=10.0)]
    out = classify_regime_rule_based(_df_from_rows(rows))
    assert out["regime_rule"].iloc[0] == "RANGE"


def test_unknown_for_nan_features():
    rows = [_base_row(atr_14=np.nan)]
    out = classify_regime_rule_based(_df_from_rows(rows))
    assert out["regime_rule"].iloc[0] == "UNKNOWN"


def test_liquidity_flags():
    high_liq = _df_from_rows([_base_row(relative_volume=2.0)])
    low_liq = _df_from_rows([_base_row(relative_volume=0.2)])
    out_high = classify_regime_rule_based(high_liq)
    out_low = classify_regime_rule_based(low_liq)
    assert bool(out_high["high_liquidity"].iloc[0]) is True
    assert bool(out_low["low_liquidity"].iloc[0]) is True


def test_missing_columns_raises():
    df = pd.DataFrame({"timestamp": [pd.Timestamp("2024-01-02", tz="America/New_York")]})
    try:
        classify_regime_rule_based(df)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_config_thresholds_are_respected():
    rows = [_base_row(volatility_percentile=0.65, true_range=5.0, atr_14=10.0)]
    strict = RegimeConfig(high_volatility_percentile=0.9)
    lenient = RegimeConfig(high_volatility_percentile=0.6)
    out_strict = classify_regime_rule_based(_df_from_rows(rows), strict)
    out_lenient = classify_regime_rule_based(_df_from_rows(rows), lenient)
    assert out_strict["regime_rule"].iloc[0] != "HIGH_VOLATILITY"
    assert out_lenient["regime_rule"].iloc[0] == "HIGH_VOLATILITY"
