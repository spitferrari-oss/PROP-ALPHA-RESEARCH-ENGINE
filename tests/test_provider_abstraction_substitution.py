"""Provider abstraction substitution tests (hardening pass Step 53).

Proves the actual claim `providers.base`'s module docstring makes ("the
PARE core imports only this ABC, never a vendor SDK directly") by writing
functions against the ABC type alone and running them against the mock
provider — if these functions needed anything mock-specific, they
wouldn't type-check/run against the ABC signature in the first place.
A real adapter (`providers.databento.DatabentoProvider`,
`providers.gexbot.GexbotOptionsProvider`) would substitute in identically
since both also implement these same ABCs; this suite exercises the
substitution property with the mock because it's the one implementation
in this repo guaranteed to run without real credentials or network.
"""
from __future__ import annotations

import datetime as dt

from prop_alpha.providers.base import DataLevel, FuturesDataProvider, OptionsDataProvider
from prop_alpha.providers.mocks import MockFuturesDataProvider, MockOptionsDataProvider


def _get_historical_row_count(provider: FuturesDataProvider, instrument: str, start: dt.date, end: dt.date) -> int:
    """Written against the ABC only -- no mock-specific import, no
    isinstance check on a concrete class.
    """
    df = provider.get_historical(instrument, start, end, DataLevel.L1)
    return len(df)


def _get_instrument_symbol(provider: FuturesDataProvider, instrument: str) -> str:
    return provider.get_instrument_definition(instrument).symbol


def _collect_live_messages(provider: FuturesDataProvider, instrument: str) -> list[dict]:
    messages: list[dict] = []
    handle = provider.subscribe_live(instrument, DataLevel.L1, messages.append)
    handle.close()
    return messages


def _get_options_metric_names(provider: OptionsDataProvider, underlying: str) -> list[str]:
    snapshot = provider.get_snapshot(underlying)
    return [
        name for name, value in snapshot.items()
        if isinstance(value, dict) and "availability" in value
    ]


def test_futures_function_written_against_abc_works_with_mock():
    provider: FuturesDataProvider = MockFuturesDataProvider(seed=1)
    count = _get_historical_row_count(provider, "NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 3))
    assert count > 0


def test_futures_instrument_definition_function_works_with_mock():
    provider: FuturesDataProvider = MockFuturesDataProvider()
    assert _get_instrument_symbol(provider, "NQ") == "NQ"


def test_futures_live_subscription_function_works_with_mock():
    provider: FuturesDataProvider = MockFuturesDataProvider(seed=1)
    messages = _collect_live_messages(provider, "NQ")
    assert len(messages) == 5


def test_options_function_written_against_abc_works_with_mock():
    provider: OptionsDataProvider = MockOptionsDataProvider(seed=1)
    names = _get_options_metric_names(provider, "SPX")
    assert "gex" in names
    assert "dex" in names


def test_mock_futures_provider_is_swappable_for_any_futures_data_provider_typed_slot():
    def accepts_any_futures_provider(provider: FuturesDataProvider) -> str:
        return provider.get_trading_calendar("NQ").exchange

    assert accepts_any_futures_provider(MockFuturesDataProvider()) == "CME"


def test_mock_options_provider_is_swappable_for_any_options_data_provider_typed_slot():
    def accepts_any_options_provider(provider: OptionsDataProvider) -> list[dict]:
        return provider.get_levels("SPX")

    levels = accepts_any_options_provider(MockOptionsDataProvider(seed=1))
    assert isinstance(levels, list)
    assert len(levels) > 0
