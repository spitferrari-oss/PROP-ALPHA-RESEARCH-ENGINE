import datetime as dt

import pandas as pd
import pytest

from prop_alpha.providers.base import (
    DataLevel,
    FuturesDataProvider,
    InstrumentDefinition,
    OptionsDataProvider,
    TradingCalendar,
)


class _StubFuturesProvider(FuturesDataProvider):
    """Minimal concrete implementation used only to prove the ABC's
    contract is satisfiable — not a real provider (that's Phase B/C).
    """
    name = "stub"

    def get_historical(self, instrument, start, end, level, schema=None):
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def subscribe_live(self, instrument, level, on_message):
        class _Handle:
            is_active = False

            def close(self):
                pass

        return _Handle()

    def get_instrument_definition(self, instrument):
        return InstrumentDefinition(
            symbol=instrument, exchange="CME", asset_class="FUTURE", currency="USD",
            tick_size=0.25, point_value=20.0,
        )

    def get_trading_calendar(self, instrument):
        return TradingCalendar(exchange="CME", timezone="America/New_York")


class _StubOptionsProvider(OptionsDataProvider):
    name = "stub"

    def get_historical(self, underlying, start, end, metrics=None):
        return pd.DataFrame()

    def get_snapshot(self, underlying):
        return {}

    def subscribe_live(self, underlying, on_message):
        class _Handle:
            is_active = False

            def close(self):
                pass

        return _Handle()

    def get_levels(self, underlying):
        return []

    def get_orderflow(self, underlying, start, end):
        return pd.DataFrame()

    def get_instrument_state(self, underlying):
        return {}


def test_data_level_satisfies_is_a_partial_order():
    assert DataLevel.L3.satisfies(DataLevel.L2)
    assert DataLevel.L2.satisfies(DataLevel.L2)
    assert not DataLevel.L1.satisfies(DataLevel.L2)
    assert DataLevel.L4.satisfies(DataLevel.L1)


def test_futures_provider_abc_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        FuturesDataProvider()


def test_options_provider_abc_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        OptionsDataProvider()


def test_incomplete_futures_provider_subclass_raises_type_error():
    class _Incomplete(FuturesDataProvider):
        name = "incomplete"

        def get_historical(self, instrument, start, end, level, schema=None):
            return pd.DataFrame()
        # missing subscribe_live/get_instrument_definition/get_trading_calendar

    with pytest.raises(TypeError):
        _Incomplete()


def test_stub_futures_provider_satisfies_the_full_interface():
    provider = _StubFuturesProvider()
    df = provider.get_historical("NQ", dt.date(2024, 1, 1), dt.date(2024, 1, 2), DataLevel.L1)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    handle = provider.subscribe_live("NQ", DataLevel.L2, on_message=lambda msg: None)
    assert handle.is_active is False
    handle.close()

    definition = provider.get_instrument_definition("NQ")
    assert definition.symbol == "NQ"
    assert definition.tick_size == 0.25

    calendar = provider.get_trading_calendar("NQ")
    assert calendar.is_trading_day(dt.date(2024, 1, 2))  # a Tuesday
    assert not calendar.is_trading_day(dt.date(2024, 1, 6))  # a Saturday


def test_trading_calendar_respects_holidays():
    calendar = TradingCalendar(
        exchange="CME", timezone="America/New_York",
        holidays=frozenset({dt.date(2024, 12, 25)}),
    )
    assert not calendar.is_trading_day(dt.date(2024, 12, 25))
    assert calendar.is_trading_day(dt.date(2024, 12, 24))


def test_stub_options_provider_satisfies_the_full_interface():
    provider = _StubOptionsProvider()
    assert provider.get_snapshot("SPX") == {}
    assert provider.get_levels("SPX") == []
    assert provider.get_instrument_state("SPX") == {}
    handle = provider.subscribe_live("SPX", on_message=lambda msg: None)
    assert handle.is_active is False
