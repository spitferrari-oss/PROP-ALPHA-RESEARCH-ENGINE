import pandas as pd

from prop_alpha.research_templates.conditions import GEX_CONDITION_LIBRARY

_COND = {c.name: c for c in GEX_CONDITION_LIBRARY}


def _df():
    return pd.DataFrame({
        "close": [100.0, 100.0, 100.0, 100.0],
        "atr_14": [1.0, 1.0, 1.0, 1.0],
        "gex_regime": ["STRONG_POSITIVE_GAMMA", "STRONG_NEGATIVE_GAMMA", "NEUTRAL", "POSITIVE_GAMMA"],
        "dex_sign": [1.0, -1.0, 0.0, 1.0],
        "options_gamma_flip": [99.5, 100.5, 100.0, 105.0],
        "options_major_positive_gamma": [95.0, 105.0, 100.0, 100.0],
        "options_major_negative_gamma": [105.0, 95.0, 100.0, 100.0],
    })


def test_library_has_expected_condition_names():
    expected = {
        "gex_regime_strong_positive", "gex_regime_positive", "gex_regime_negative",
        "gex_regime_strong_negative", "gex_regime_neutral", "dex_sign_positive", "dex_sign_negative",
        "above_gamma_flip", "below_gamma_flip", "near_gamma_flip",
        "above_major_positive_gamma", "below_major_negative_gamma",
    }
    assert expected == set(_COND.keys())


def test_gex_regime_strong_positive_fires_only_on_matching_rows():
    result = _COND["gex_regime_strong_positive"].fn(_df())
    assert list(result) == [True, False, False, False]


def test_gex_regime_positive_includes_strong_positive():
    result = _COND["gex_regime_positive"].fn(_df())
    assert list(result) == [True, False, False, True]


def test_gex_regime_negative_includes_strong_negative():
    result = _COND["gex_regime_negative"].fn(_df())
    assert list(result) == [False, True, False, False]


def test_dex_sign_positive_and_negative_are_mutually_exclusive():
    positive = _COND["dex_sign_positive"].fn(_df())
    negative = _COND["dex_sign_negative"].fn(_df())
    assert list(positive) == [True, False, False, True]
    assert list(negative) == [False, True, False, False]
    assert not (positive & negative).any()


def test_above_and_below_gamma_flip():
    above = _COND["above_gamma_flip"].fn(_df())
    below = _COND["below_gamma_flip"].fn(_df())
    assert list(above) == [True, False, False, False]
    assert list(below) == [False, True, False, True]


def test_near_gamma_flip_within_one_atr():
    result = _COND["near_gamma_flip"].fn(_df())
    # row 0: |100-99.5|=0.5 < 1 atr -> True; row 1: |100-100.5|=0.5 < 1 -> True
    # row 2: |100-100|=0 < 1 -> True; row 3: |100-105|=5 >= 1 -> False
    assert list(result) == [True, True, True, False]


def test_above_major_positive_gamma_and_below_major_negative_gamma():
    above = _COND["above_major_positive_gamma"].fn(_df())
    below = _COND["below_major_negative_gamma"].fn(_df())
    assert list(above) == [True, False, False, False]
    assert list(below) == [True, False, False, False]


def test_every_condition_has_a_mechanism_hint():
    for condition in GEX_CONDITION_LIBRARY:
        assert condition.mechanism_hint
        assert isinstance(condition.mechanism_hint, str)
