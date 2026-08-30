import datetime as dt
import sys
import types

import pandas as pd
import pytest

from prop_alpha.providers.base import DataLevel
from prop_alpha.providers.databento.historical import DatabentoHistoricalMixin


class _FakeStore:
    def __init__(self, df):
        self._df = df

    def to_df(self):
        return self._df


class _FakeClient:
    """Mimics Databento's Historical client: `.timeseries.get_range(...).to_df()`.
    Used so these tests never touch the network or need a real API key
    (extension §134/§136).
    """
    def __init__(self, df):
        self._df = df
        self.calls = []
        self.timeseries = self

    def get_range(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeStore(self._df)


def _ohlcv_fixture():
    idx = pd.date_range("2024-01-02", periods=3, freq="1min", tz="UTC")
    idx.name = "ts_event"
    return pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [100.5, 101.5, 102.5],
        "low": [99.5, 100.5, 101.5],
        "close": [100.2, 101.2, 102.2],
        "volume": [10, 20, 30],
        "symbol": ["NQZ4", "NQZ4", "NQZ4"],
    }, index=idx)


def test_get_historical_ohlcv_normalizes_to_canonical_schema():
    client = _FakeClient(_ohlcv_fixture())
    provider = DatabentoHistoricalMixin(client=client)
    df = provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 3), DataLevel.L1)

    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume", "buy_volume", "sell_volume"]
    assert df["timestamp"].dt.tz is not None
    assert df.attrs["source"] == "DATABENTO"
    assert df.attrs["symbol"] == "NQ"
    assert df.attrs["schema"] == "ohlcv-1m"
    assert df.attrs["dataset"] == "GLBX.MDP3"

    call = client.calls[0]
    assert call["dataset"] == "GLBX.MDP3"
    assert call["symbols"] == ["NQ.c.0"]
    assert call["schema"] == "ohlcv-1m"
    assert call["stype_in"] == "continuous"
    assert call["start"] == "2024-01-02"
    assert call["end"] == "2024-01-03"


def test_get_historical_respects_explicit_schema_override():
    client = _FakeClient(_ohlcv_fixture())
    provider = DatabentoHistoricalMixin(client=client)
    provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 3), DataLevel.L1, schema="ohlcv-1h")
    assert client.calls[0]["schema"] == "ohlcv-1h"


def test_get_historical_non_ohlcv_schema_keeps_native_columns():
    idx = pd.date_range("2024-01-02", periods=2, freq="1s", tz="UTC")
    idx.name = "ts_event"
    raw_df = pd.DataFrame({"price": [100.25, 100.5], "size": [1, 2], "side": ["A", "B"]}, index=idx)
    client = _FakeClient(raw_df)
    provider = DatabentoHistoricalMixin(client=client)

    df = provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 3), DataLevel.L2)

    assert "timestamp" in df.columns
    assert "price" in df.columns and "size" in df.columns
    assert client.calls[0]["schema"] == "trades"


def test_get_historical_ohlcv_missing_column_raises():
    idx = pd.date_range("2024-01-02", periods=1, freq="1min", tz="UTC")
    idx.name = "ts_event"
    raw_df = pd.DataFrame({"open": [100.0], "high": [100.5], "low": [99.5]}, index=idx)  # no close/volume
    client = _FakeClient(raw_df)
    provider = DatabentoHistoricalMixin(client=client)

    with pytest.raises(ValueError, match="missing expected column"):
        provider.get_historical("NQ", dt.date(2024, 1, 2), dt.date(2024, 1, 3), DataLevel.L1)


def test_get_historical_unknown_instrument_raises_dataset_required():
    provider = DatabentoHistoricalMixin(client=object())
    with pytest.raises(ValueError, match="DATASET_REQUIRED"):
        provider.get_historical("ZZZZ", dt.date(2024, 1, 1), dt.date(2024, 1, 2), DataLevel.L1)


def test_get_instrument_definition_returns_symbology_metadata():
    provider = DatabentoHistoricalMixin(client=object())
    definition = provider.get_instrument_definition("ES")
    assert definition.symbol == "ES"
    assert definition.exchange == "CME"
    assert definition.point_value == 50.0
    assert definition.tick_size == 0.25


def test_get_trading_calendar_uses_symbology_timezone():
    provider = DatabentoHistoricalMixin(client=object())
    calendar = provider.get_trading_calendar("DAX")
    assert calendar.exchange == "EUREX"
    assert calendar.timezone == "Europe/Berlin"


def test_no_client_and_databento_not_installed_raises_clear_runtime_error():
    provider = DatabentoHistoricalMixin(client=None, api_key="dummy")
    with pytest.raises(RuntimeError, match="not installed"):
        provider.get_historical("NQ", dt.date(2024, 1, 1), dt.date(2024, 1, 2), DataLevel.L1)


def test_no_api_key_raises_clear_runtime_error(monkeypatch):
    fake_module = types.ModuleType("databento")
    fake_module.Historical = lambda key: None
    monkeypatch.setitem(sys.modules, "databento", fake_module)
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)

    provider = DatabentoHistoricalMixin()
    with pytest.raises(RuntimeError, match="No Databento API key"):
        provider.get_historical("NQ", dt.date(2024, 1, 1), dt.date(2024, 1, 2), DataLevel.L1)
