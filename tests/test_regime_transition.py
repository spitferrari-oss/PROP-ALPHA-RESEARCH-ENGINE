import pandas as pd

from prop_alpha.config import RegimeConfig
from prop_alpha.regimes.transition import compute_transition_flags


def test_stable_regime_not_flagged():
    df = pd.DataFrame({"regime_rule": ["TREND_UP"] * 10})
    out = compute_transition_flags(df, RegimeConfig(transition_lookback_bars=3))
    assert not out["regime_transitioning"].any()


def test_whipsawing_regime_flagged():
    df = pd.DataFrame({"regime_rule": ["TREND_UP", "RANGE", "TREND_DOWN", "RANGE", "TREND_UP"] * 2})
    out = compute_transition_flags(df, RegimeConfig(transition_lookback_bars=3))
    assert out["regime_transitioning"].any()


def test_single_regime_change_not_enough_to_flag():
    # One change in a 3-bar lookback (flip_count==1) should not trip the
    # >=2 threshold used to call a label "unstable".
    df = pd.DataFrame({"regime_rule": ["TREND_UP"] * 5 + ["RANGE"] * 5})
    out = compute_transition_flags(df, RegimeConfig(transition_lookback_bars=3))
    # only the single bar where the flip itself occurs should have flip_count==1, not >=2
    assert out["regime_transitioning"].sum() == 0


def test_low_confidence_flags_transition():
    df = pd.DataFrame({
        "regime_rule": ["TREND_UP"] * 5,
        "regime_gmm_confidence": [0.9, 0.9, 0.3, 0.9, 0.9],
    })
    out = compute_transition_flags(df, RegimeConfig(transition_confidence_threshold=0.5))
    assert out["regime_transitioning"].tolist() == [False, False, True, False, False]


def test_missing_columns_default_to_no_flag():
    df = pd.DataFrame({"close": [1, 2, 3]})
    out = compute_transition_flags(df)
    assert not out["regime_transitioning"].any()
