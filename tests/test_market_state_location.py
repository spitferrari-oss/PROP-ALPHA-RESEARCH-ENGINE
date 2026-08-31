import datetime as dt

import pytest

from prop_alpha.market_state.location import build_market_location
from prop_alpha.options.models import (
    AvailabilityStatus,
    LevelType,
    Metric,
    MetricAvailability,
    OptionsLevel,
)

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _level(metric: str, value: float) -> OptionsLevel:
    return OptionsLevel(
        underlying="ES", timestamp=_NOW, strike=4500.0, type=LevelType.GAMMA_FLIP,
        value=value, distance_from_spot=None, source="gexbot", metric=metric,
    )


def test_build_market_location_includes_present_futures_columns():
    futures_bar = {"vwap": 4500.0, "prior_day_high": 4520.0, "prior_day_low": 4480.0}
    location = build_market_location(futures_bar, price=4510.0, timestamp=_NOW)

    names = {d.name for d in location.distances}
    assert names == {"vwap", "prior_day_high", "prior_day_low"}
    vwap_distance = location.get("vwap")
    assert vwap_distance.absolute == pytest.approx(10.0)
    assert vwap_distance.category == "futures"


def test_build_market_location_skips_missing_or_nan_columns():
    futures_bar = {"vwap": 4500.0, "volume_profile_poc": None, "prior_day_high": float("nan")}
    location = build_market_location(futures_bar, price=4510.0, timestamp=_NOW)
    names = {d.name for d in location.distances}
    assert names == {"vwap"}


def test_build_market_location_includes_options_levels_with_options_prefix():
    futures_bar = {"vwap": 4500.0}
    levels = [_level("gamma_flip", 4495.0), _level("major_positive_gamma", 4550.0)]
    location = build_market_location(futures_bar, price=4510.0, timestamp=_NOW, options_levels=levels)

    options_distances = [d for d in location.distances if d.category == "options"]
    assert {d.name for d in options_distances} == {"options_gamma_flip", "options_major_positive_gamma"}


def test_build_market_location_skips_options_levels_with_none_value():
    levels = [_level("gamma_flip", None)]
    location = build_market_location({}, price=4510.0, timestamp=_NOW, options_levels=levels)
    assert location.distances == []


def test_atr_normalization_applied_when_atr_given():
    futures_bar = {"vwap": 4500.0}
    location = build_market_location({"vwap": 4500.0}, price=4520.0, timestamp=_NOW, atr=10.0)
    vwap_distance = location.get("vwap")
    assert vwap_distance.atr_normalized == pytest.approx(2.0)


def test_atr_normalized_none_without_atr():
    location = build_market_location({"vwap": 4500.0}, price=4520.0, timestamp=_NOW)
    assert location.get("vwap").atr_normalized is None


def test_as_dict_prefers_atr_normalized_falls_back_to_percentage():
    with_atr = build_market_location({"vwap": 4500.0}, price=4520.0, timestamp=_NOW, atr=10.0)
    without_atr = build_market_location({"vwap": 4500.0}, price=4520.0, timestamp=_NOW)

    assert with_atr.as_dict()["vwap"] == pytest.approx(2.0)
    assert without_atr.as_dict()["vwap"] == pytest.approx(20.0 / 4520.0)


def test_get_returns_none_for_unknown_name():
    location = build_market_location({"vwap": 4500.0}, price=4510.0, timestamp=_NOW)
    assert location.get("nonexistent") is None


def test_empty_futures_bar_and_no_options_levels_yields_no_distances():
    location = build_market_location({}, price=4510.0, timestamp=_NOW)
    assert location.distances == []
    assert location.as_dict() == {}
