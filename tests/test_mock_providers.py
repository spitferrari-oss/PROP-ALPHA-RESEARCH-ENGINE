import datetime as dt

import pandas as pd
import pytest

from prop_alpha.providers.base import FuturesDataProvider, OptionsDataProvider
from prop_alpha.providers.mocks import MockFuturesDataProvider, MockOptionsDataProvider


def test_mock_futures_provider_satisfies_the_abc():
    provider = MockFuturesDataProvider()
    assert isinstance(provider, FuturesDataProvider)


def test_mock_options_provider_satisfies_the_abc():
    provider = MockOptionsDataProvider()
    assert isinstance(provider, OptionsDataProvider)


def test_get_historical_returns_required_schema_columns():
    provider = MockFuturesDataProvider(seed=1)
    df = provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 5), level=None)
    for col in ("timestamp", "open", "high", "low", "close", "volume"):
        assert col in df.columns
    assert not df.empty


def test_get_historical_timestamps_are_utc():
    provider = MockFuturesDataProvider(seed=1)
    df = provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 5), level=None)
    assert str(df["timestamp"].dt.tz) == "UTC"


def test_get_historical_filters_to_requested_range():
    provider = MockFuturesDataProvider(seed=1)
    df = provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 2), level=None)
    assert (df["timestamp"].dt.date == dt.date(2024, 1, 2)).all()


def test_get_historical_is_deterministic_for_a_fixed_seed():
    a = MockFuturesDataProvider(seed=7).get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 5), level=None)
    b = MockFuturesDataProvider(seed=7).get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 5), level=None)
    pd.testing.assert_frame_equal(a, b)


def test_futures_subscribe_live_delivers_messages_synchronously():
    provider = MockFuturesDataProvider(seed=1)
    received = []
    handle = provider.subscribe_live("NQ", level=None, on_message=received.append)
    assert len(received) == 5
    assert handle.is_active is False
    handle.close()  # no-op, should not raise


def test_get_instrument_definition_and_trading_calendar():
    provider = MockFuturesDataProvider()
    definition = provider.get_instrument_definition("NQ")
    assert definition.symbol == "NQ"
    calendar = provider.get_trading_calendar("NQ")
    assert calendar.is_trading_day(dt.date(2024, 1, 2))  # Tuesday
    assert not calendar.is_trading_day(dt.date(2024, 1, 6))  # Saturday


def test_options_get_snapshot_returns_normalized_shape():
    provider = MockOptionsDataProvider(seed=1)
    snapshot = provider.get_snapshot("SPX")
    assert snapshot["underlying"] == "SPX"
    for metric in ("spot", "gex", "dex", "gamma_flip"):
        assert "value" in snapshot[metric]
        assert "availability" in snapshot[metric]


def test_options_get_snapshot_is_deterministic_for_a_fixed_seed():
    a = MockOptionsDataProvider(seed=3).get_snapshot("SPX")
    b = MockOptionsDataProvider(seed=3).get_snapshot("SPX")
    assert a["gex"]["value"] == b["gex"]["value"]


def test_options_subscribe_live_delivers_one_snapshot():
    provider = MockOptionsDataProvider(seed=1)
    received = []
    handle = provider.subscribe_live("SPX", on_message=received.append)
    assert len(received) == 1
    assert handle.is_active is False


def test_options_get_levels_returns_gamma_flip_level():
    provider = MockOptionsDataProvider(seed=1)
    levels = provider.get_levels("SPX")
    assert any(level["metric"] == "gamma_flip" for level in levels)


def test_options_get_orderflow_raises_not_implemented():
    provider = MockOptionsDataProvider()
    with pytest.raises(NotImplementedError, match="order flow"):
        provider.get_orderflow("SPX", dt.date(2024, 1, 2), dt.date(2024, 1, 5))


def test_options_get_instrument_state_lists_available_metrics():
    provider = MockOptionsDataProvider(seed=1)
    state = provider.get_instrument_state("SPX")
    assert state["underlying"] == "SPX"
    assert "gex" in state["available_metrics"]


def test_options_get_historical_returns_one_row_per_business_day():
    provider = MockOptionsDataProvider(seed=1)
    df = provider.get_historical("SPX", dt.date(2024, 1, 2), dt.date(2024, 1, 5))
    assert len(df) == len(pd.bdate_range(start=dt.date(2024, 1, 2), end=dt.date(2024, 1, 5)))


def test_options_get_historical_filters_to_requested_metrics():
    provider = MockOptionsDataProvider(seed=1)
    df = provider.get_historical("SPX", dt.date(2024, 1, 2), dt.date(2024, 1, 5), metrics=["gex"])
    assert set(df.columns) == {"timestamp", "gex"}


def test_generate_snapshot_sequence_is_time_ordered_and_spaced():
    provider = MockOptionsDataProvider(seed=1)
    start = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)
    snapshots = provider.generate_snapshot_sequence("SPX", start, n=3, interval_seconds=30.0)
    assert len(snapshots) == 3
    assert [s.timestamp for s in snapshots] == [
        start, start + dt.timedelta(seconds=30), start + dt.timedelta(seconds=60),
    ]


def test_generate_snapshot_sequence_values_vary_across_snapshots():
    provider = MockOptionsDataProvider(seed=1)
    start = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)
    snapshots = provider.generate_snapshot_sequence("SPX", start, n=3, interval_seconds=30.0)
    gex_values = [s.gex.value for s in snapshots]
    assert len(set(gex_values)) > 1
