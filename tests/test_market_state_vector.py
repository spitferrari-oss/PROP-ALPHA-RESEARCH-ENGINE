import datetime as dt

import pytest

from prop_alpha.market_state.location import LocationDistance, MarketLocation
from prop_alpha.market_state.vector import (
    attach_market_state,
    build_market_state,
    build_market_state_from_cross_market,
)
from prop_alpha.options.models import AvailabilityStatus, Metric, MetricAvailability, OptionsSnapshot
from prop_alpha.sync.cross_market import CrossMarketState

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _metric(value, status=AvailabilityStatus.AVAILABLE) -> Metric:
    return Metric(value=value, availability=MetricAvailability(status=status, timestamp=_NOW, source="gexbot", freshness_seconds=0.0))


def _snapshot(**overrides) -> OptionsSnapshot:
    fields = dict(
        spot=_metric(4500.0), gex=_metric(1.5e9), dex=_metric(2.0e8), gamma_flip=_metric(4490.0),
        major_positive_gamma=_metric(4550.0), major_negative_gamma=_metric(4450.0),
        vanna=_metric(None, AvailabilityStatus.UNAVAILABLE), charm=_metric(None, AvailabilityStatus.UNAVAILABLE),
        vomma=_metric(None, AvailabilityStatus.UNAVAILABLE), skew=_metric(0.1), options_volume=_metric(100000),
        open_interest=_metric(500000),
    )
    fields.update(overrides)
    return OptionsSnapshot(timestamp=_NOW, underlying="ES", **fields)


def test_build_market_state_extracts_known_columns_only():
    futures_bar = {
        "open": 4500.0, "high": 4510.0, "low": 4495.0, "close": 4505.0, "vwap": 4502.0,
        "volume": 1000.0, "unrelated_column": 123.0, "atr": 12.0, "regime_rule": "TRENDING",
    }
    state = build_market_state(futures_bar, timestamp=_NOW)

    assert state.price_state == {"open": 4500.0, "high": 4510.0, "low": 4495.0, "close": 4505.0, "vwap": 4502.0}
    assert state.volume_state == {"volume": 1000.0}
    assert state.volatility_state == {"atr": 12.0}
    assert state.regime_state == {"regime_rule": "TRENDING"}
    assert "unrelated_column" not in state.as_flat_dict().values()


def test_build_market_state_missing_columns_leave_component_empty():
    state = build_market_state({}, timestamp=_NOW)
    assert state.price_state == {}
    assert state.liquidity_state == {}
    assert state.completeness == 0.0


def test_build_market_state_nan_values_are_excluded():
    futures_bar = {"open": float("nan"), "close": 4505.0}
    state = build_market_state(futures_bar, timestamp=_NOW)
    assert state.price_state == {"close": 4505.0}


def test_build_market_state_event_state_defaults_empty_and_passthrough():
    default_state = build_market_state({}, timestamp=_NOW)
    assert default_state.event_state == {}

    passed_state = build_market_state({}, timestamp=_NOW, event_state={"earnings_in_minutes": 30})
    assert passed_state.event_state == {"earnings_in_minutes": 30}


def test_build_market_state_options_snapshot_flattens_value_and_status():
    state = build_market_state({}, timestamp=_NOW, options_snapshot=_snapshot())
    assert state.options_state["gex"] == pytest.approx(1.5e9)
    assert state.options_state["gex_status"] == AvailabilityStatus.AVAILABLE.value
    # unavailable metric: no value key, but status key still present
    assert "vanna" not in state.options_state
    assert state.options_state["vanna_status"] == AvailabilityStatus.UNAVAILABLE.value


def test_build_market_state_location_distances_split_by_category():
    location = MarketLocation(
        timestamp=_NOW, price=4510.0,
        distances=[
            LocationDistance(name="vwap", category="futures", absolute=10.0, percentage=0.0022, atr_normalized=1.0, vol_normalized=None),
            LocationDistance(name="options_gamma_flip", category="options", absolute=20.0, percentage=0.0044, atr_normalized=2.0, vol_normalized=None),
        ],
    )
    state = build_market_state({}, timestamp=_NOW, market_location=location)
    assert state.profile_state == {"distance_to_vwap": 1.0}
    assert state.options_state == {"distance_to_options_gamma_flip": 2.0}


def test_completeness_reflects_populated_components():
    state = build_market_state({"close": 4505.0, "volume": 100.0}, timestamp=_NOW)
    # price_state + volume_state populated out of 10 components
    assert state.completeness == pytest.approx(2 / 10)


def test_as_flat_dict_namespaces_by_component():
    state = build_market_state({"close": 4505.0}, timestamp=_NOW)
    flat = state.as_flat_dict()
    assert flat == {"price_state.close": 4505.0}


def test_build_market_state_from_cross_market_extracts_futures_options_timestamp():
    cross = CrossMarketState(
        timestamp=_NOW, futures={"close": 4505.0}, options=_snapshot(), sync_time_difference_ms=50.0,
    )
    state = build_market_state_from_cross_market(cross)
    assert state.price_state == {"close": 4505.0}
    assert state.options_state["gex"] == pytest.approx(1.5e9)
    assert state.timestamp == _NOW


def test_attach_market_state_returns_new_instance_with_flat_dict_and_does_not_mutate_original():
    cross = CrossMarketState(
        timestamp=_NOW, futures={"close": 4505.0}, options=None, sync_time_difference_ms=None,
    )
    attached = attach_market_state(cross)

    assert cross.market_state is None
    assert attached is not cross
    assert attached.market_state == {"price_state.close": 4505.0}
    assert attached.futures == cross.futures
