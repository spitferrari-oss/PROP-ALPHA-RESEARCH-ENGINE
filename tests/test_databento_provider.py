import datetime as dt

import pandas as pd

from prop_alpha.providers.base import DataLevel, FuturesDataProvider
from prop_alpha.providers.databento import DatabentoProvider


class _FakeHistoricalStore:
    def __init__(self, df):
        self._df = df

    def to_df(self):
        return self._df


class _FakeHistoricalClient:
    def __init__(self, df):
        self._df = df
        self.timeseries = self

    def get_range(self, **kwargs):
        return _FakeHistoricalStore(self._df)


class _FakeLiveClient:
    def __init__(self):
        self.started = False
        self._callback = None

    def subscribe(self, **kwargs):
        pass

    def add_callback(self, callback):
        self._callback = callback

    def start(self):
        self.started = True

    def stop(self):
        pass

    def fire(self, raw):
        self._callback(raw)


def _ohlcv_fixture():
    idx = pd.date_range("2024-01-02", periods=2, freq="1min", tz="UTC")
    idx.name = "ts_event"
    return pd.DataFrame({
        "open": [100.0, 101.0], "high": [100.5, 101.5], "low": [99.5, 100.5],
        "close": [100.2, 101.2], "volume": [10, 20],
    }, index=idx)


def test_databento_provider_satisfies_futures_data_provider_abc():
    provider = DatabentoProvider(client=object(), live_client=object())
    assert isinstance(provider, FuturesDataProvider)


def test_databento_provider_get_historical_delegates_to_historical_mixin():
    provider = DatabentoProvider(client=_FakeHistoricalClient(_ohlcv_fixture()))
    df = provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 3), DataLevel.L1)
    assert df.attrs["source"] == "DATABENTO"
    assert list(df.columns[:6]) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_databento_provider_subscribe_live_delegates_to_live_mixin():
    live_client = _FakeLiveClient()
    provider = DatabentoProvider(live_client=live_client)
    received = []
    handle = provider.subscribe_live("NQ", DataLevel.L1, on_message=received.append)

    assert live_client.started
    assert handle.is_active
    live_client.fire({"ts_event": 1_700_000_000_000_000_000, "open": 100.0})
    assert received == [{"ts_event": 1_700_000_000_000_000_000, "open": 100.0}]

    handle.close()
    assert not handle.is_active


def test_databento_provider_instrument_definition_and_calendar():
    provider = DatabentoProvider(client=object(), live_client=object())
    definition = provider.get_instrument_definition("ES")
    assert definition.point_value == 50.0
    calendar = provider.get_trading_calendar("ES")
    assert calendar.exchange == "CME"
