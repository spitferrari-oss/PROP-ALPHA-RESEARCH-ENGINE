import datetime as dt
import sys
import types

import pytest

from prop_alpha.data.live.recorder import LiveRecorder
from prop_alpha.data.live.subscription_manager import SubscriptionManager
from prop_alpha.providers.base import DataLevel
from prop_alpha.providers.databento.live import DatabentoLiveMixin, _coerce_timestamp


class _FakeLiveClient:
    """Mimics Databento's Live client: subscribe/add_callback/start/stop,
    with a `fire()` test helper to simulate an inbound message reaching the
    registered callback. No network access needed (extension §134/§136).
    """
    def __init__(self):
        self.subscribe_calls = []
        self.started = False
        self.stopped = False
        self._callback = None

    def subscribe(self, **kwargs):
        self.subscribe_calls.append(kwargs)

    def add_callback(self, callback):
        self._callback = callback

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def fire(self, raw: dict):
        assert self._callback is not None, "no callback registered yet"
        self._callback(raw)


def test_subscribe_live_connects_and_subscribes_with_symbology():
    client = _FakeLiveClient()
    provider = DatabentoLiveMixin(live_client=client)
    handle = provider.subscribe_live("NQ", DataLevel.L2, on_message=lambda raw: None)

    assert client.started
    assert handle.is_active
    call = client.subscribe_calls[0]
    assert call["dataset"] == "GLBX.MDP3"
    assert call["symbols"] == ["NQ.c.0"]
    assert call["schema"] == "trades"
    assert call["stype_in"] == "continuous"


def test_subscribe_live_records_and_delivers_messages():
    client = _FakeLiveClient()
    recorder = LiveRecorder()
    provider = DatabentoLiveMixin(live_client=client, recorder=recorder)
    received = []
    provider.subscribe_live("NQ", DataLevel.L1, on_message=received.append)

    client.fire({"ts_event": 1_700_000_000_000_000_000, "sequence": 1, "open": 100.0})
    client.fire({"ts_event": 1_700_000_000_100_000_000, "sequence": 2, "open": 100.5})

    assert recorder.message_count == 2
    assert len(received) == 2
    assert received[0]["open"] == 100.0


def test_subscribe_live_dispatches_through_event_router():
    from prop_alpha.data.live.event_router import EventRouter

    client = _FakeLiveClient()
    router = EventRouter()
    provider = DatabentoLiveMixin(live_client=client, event_router=router)
    routed = []
    router.subscribe(routed.append, provider="databento", instrument="NQ")
    provider.subscribe_live("NQ", DataLevel.L1, on_message=lambda raw: None)

    client.fire({"ts_event": 1_700_000_000_000_000_000, "sequence": 1})
    assert len(routed) == 1
    assert routed[0].instrument == "NQ"


def test_subscribe_live_rejects_duplicate_subscription():
    client = _FakeLiveClient()
    subscription_manager = SubscriptionManager()
    provider = DatabentoLiveMixin(live_client=client, subscription_manager=subscription_manager)
    provider.subscribe_live("NQ", DataLevel.L1, on_message=lambda raw: None)

    with pytest.raises(RuntimeError, match="Already subscribed"):
        provider.subscribe_live("NQ", DataLevel.L1, on_message=lambda raw: None)


def test_handle_close_disconnects_and_allows_resubscription():
    client = _FakeLiveClient()
    provider = DatabentoLiveMixin(live_client=client)
    handle = provider.subscribe_live("NQ", DataLevel.L1, on_message=lambda raw: None)

    handle.close()
    assert client.stopped
    assert not handle.is_active
    handle.close()  # idempotent, must not raise
    assert provider._subscription_manager.active_keys() == []


def test_subscribe_live_unknown_instrument_raises_dataset_required():
    provider = DatabentoLiveMixin(live_client=_FakeLiveClient())
    with pytest.raises(ValueError, match="DATASET_REQUIRED"):
        provider.subscribe_live("ZZZZ", DataLevel.L1, on_message=lambda raw: None)


def test_no_live_client_and_databento_not_installed_raises_clear_runtime_error():
    provider = DatabentoLiveMixin(live_client=None, api_key="dummy")
    with pytest.raises(RuntimeError, match="not installed"):
        provider.subscribe_live("NQ", DataLevel.L1, on_message=lambda raw: None)


def test_no_api_key_raises_clear_runtime_error(monkeypatch):
    fake_module = types.ModuleType("databento")
    fake_module.Live = lambda key: None
    monkeypatch.setitem(sys.modules, "databento", fake_module)
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)

    provider = DatabentoLiveMixin()
    with pytest.raises(RuntimeError, match="No Databento API key"):
        provider.subscribe_live("NQ", DataLevel.L1, on_message=lambda raw: None)


def test_coerce_timestamp_handles_ns_epoch_datetime_and_none():
    assert _coerce_timestamp(None) is None

    naive = dt.datetime(2024, 1, 1, 12, 0, 0)
    coerced_naive = _coerce_timestamp(naive)
    assert coerced_naive.tzinfo is not None

    aware = dt.datetime(2024, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
    assert _coerce_timestamp(aware) == aware

    ns_epoch = 1_700_000_000_000_000_000
    coerced_ns = _coerce_timestamp(ns_epoch)
    assert coerced_ns.tzinfo is not None
    assert coerced_ns.year == 2023

    assert _coerce_timestamp("not-a-timestamp") is None
