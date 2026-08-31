import datetime as dt

import pytest

from prop_alpha.providers.base import OptionsDataProvider
from prop_alpha.providers.gexbot import GexbotOptionsProvider


class _FakeHandle:
    is_active = True

    def close(self):
        pass


class _FakeClient:
    def __init__(self, gex_response):
        self.gex_response = gex_response
        self.poll_calls = []

    def get_gex(self, underlying):
        return self.gex_response

    def start_polling(self, underlying, interval_seconds, callback):
        self.poll_calls.append((underlying, interval_seconds))
        callback(self.gex_response)
        return _FakeHandle()


def _raw():
    # A dynamic "now" timestamp — GexbotOptionsProvider's default
    # stale_after_seconds=60.0 would otherwise flag a hardcoded past date
    # as STALE against the real wall clock.
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return {"timestamp": now, "gex": 1.0e9, "spot": 4500.0}


def test_gexbot_provider_satisfies_options_data_provider_abc():
    provider = GexbotOptionsProvider(client=_FakeClient(_raw()))
    assert isinstance(provider, OptionsDataProvider)


def test_get_snapshot_returns_dict_with_metric_structure():
    provider = GexbotOptionsProvider(client=_FakeClient(_raw()))
    snapshot = provider.get_snapshot("SPX")
    assert snapshot["underlying"] == "SPX"
    assert snapshot["gex"]["value"] == 1.0e9
    assert snapshot["gex"]["availability"]["status"] == "AVAILABLE"
    assert snapshot["vanna"]["value"] is None
    assert snapshot["vanna"]["availability"]["status"] == "UNAVAILABLE"


def test_subscribe_live_delegates_to_client_start_polling():
    raw = _raw()
    client = _FakeClient(raw)
    provider = GexbotOptionsProvider(client=client, poll_interval_seconds=2.0)
    received = []
    handle = provider.subscribe_live("SPX", on_message=received.append)
    assert client.poll_calls == [("SPX", 2.0)]
    assert received == [raw]
    assert handle.is_active


def test_get_instrument_state_lists_available_metrics_only():
    provider = GexbotOptionsProvider(client=_FakeClient(_raw()))
    state = provider.get_instrument_state("SPX")
    assert state["underlying"] == "SPX"
    assert set(state["available_metrics"]) == {"gex", "spot"}


def test_get_historical_raises_not_implemented():
    provider = GexbotOptionsProvider(client=_FakeClient(_raw()))
    with pytest.raises(NotImplementedError, match="historical retention"):
        provider.get_historical("SPX", dt.date(2024, 1, 1), dt.date(2024, 1, 2))


def test_get_levels_returns_gamma_flip_and_major_gamma_levels():
    raw = _raw()
    raw["gamma_flip"] = 4480.0
    raw["major_positive_gamma"] = 4550.0
    provider = GexbotOptionsProvider(client=_FakeClient(raw))
    levels = provider.get_levels("SPX")
    types = {level["type"] for level in levels}
    assert "GAMMA_FLIP" in types
    assert "MAJOR_GAMMA" in types
    for level in levels:
        assert level["underlying"] == "SPX"
        assert level["source"] == "gexbot"


def test_get_orderflow_raises_not_implemented():
    provider = GexbotOptionsProvider(client=_FakeClient(_raw()))
    with pytest.raises(NotImplementedError):
        provider.get_orderflow("SPX", dt.date(2024, 1, 1), dt.date(2024, 1, 2))
