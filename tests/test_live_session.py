import datetime as dt

import pytest

from prop_alpha.data.lake import DataLakePaths
from prop_alpha.data.live.recorder import LiveRecorder, build_envelope
from prop_alpha.data.live.session import record_live_session
from prop_alpha.data.recording_config import RecordingConfig
from prop_alpha.providers.base import DataLevel


class _FakeHandle:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeProvider:
    name = "fake"

    def __init__(self, recorder: LiveRecorder, n_messages_to_fire: int = 3):
        self.recorder = recorder
        self._n = n_messages_to_fire
        self.subscribed = None
        self.handle = None

    def subscribe_live(self, instrument, level, on_message):
        self.subscribed = (instrument, level)
        for i in range(self._n):
            envelope = build_envelope(
                provider=self.name, instrument=instrument, schema="trades", payload={"i": i},
            )
            self.recorder.record(envelope)
            on_message({"i": i})
        self.handle = _FakeHandle()
        return self.handle


def test_record_live_session_writes_partitioned_output_and_counts_messages(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    provider_holder = {}

    def factory(recorder):
        provider = _FakeProvider(recorder, n_messages_to_fire=4)
        provider_holder["provider"] = provider
        return provider

    result = record_live_session(
        provider_factory=factory, provider_name="fake", instrument="NQ", level=DataLevel.L2,
        schema_for_path="trades", lake=lake, duration_seconds=1.0,
        date=dt.date(2026, 8, 30), sleep_fn=lambda s: None,
    )

    assert result.message_count == 4
    assert result.recorded is True
    expected_path = lake.partition_path("raw", "fake", "NQ", "trades", dt.date(2026, 8, 30))
    assert result.output_path == str(expected_path)
    assert expected_path.exists()
    assert len(expected_path.read_text().strip().splitlines()) == 4
    assert provider_holder["provider"].handle.closed
    assert provider_holder["provider"].subscribed == ("NQ", DataLevel.L2)


def test_record_live_session_closes_handle_even_if_sleep_raises(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    provider_holder = {}

    def factory(recorder):
        provider = _FakeProvider(recorder, n_messages_to_fire=1)
        provider_holder["provider"] = provider
        return provider

    def raising_sleep(seconds):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        record_live_session(
            provider_factory=factory, provider_name="fake", instrument="NQ", level=DataLevel.L1,
            schema_for_path="ohlcv-1m", lake=lake, duration_seconds=5.0,
            date=dt.date(2026, 8, 30), sleep_fn=raising_sleep,
        )

    assert provider_holder["provider"].handle.closed


def test_record_live_session_rejects_non_positive_duration(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    with pytest.raises(ValueError, match="must be positive"):
        record_live_session(
            provider_factory=lambda recorder: None, provider_name="fake", instrument="NQ",
            level=DataLevel.L1, schema_for_path="ohlcv-1m", lake=lake, duration_seconds=0,
        )


def test_record_live_session_disabled_config_is_a_no_op(tmp_path):
    lake = DataLakePaths(root=tmp_path / "lake")
    called = {"factory_called": False}

    def factory(recorder):
        called["factory_called"] = True
        return _FakeProvider(recorder)

    result = record_live_session(
        provider_factory=factory, provider_name="fake", instrument="NQ", level=DataLevel.L1,
        schema_for_path="ohlcv-1m", lake=lake, duration_seconds=1.0,
        config=RecordingConfig(enabled=False), sleep_fn=lambda s: None,
    )

    assert result.recorded is False
    assert result.message_count == 0
    assert called["factory_called"] is False
    assert not (lake.root / "raw").exists()
