import datetime as dt
import json

import pytest

from prop_alpha.data.live.recorder import LiveMessageEnvelope, LiveRecorder, build_envelope


def _utc(seconds: int) -> dt.datetime:
    return dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=seconds)


def test_build_envelope_prefers_exchange_timestamp_as_normalized():
    envelope = build_envelope(
        provider="databento", instrument="NQ", schema="trades", payload={"price": 100.0},
        timestamp_exchange=_utc(0), timestamp_provider=_utc(1), received_at=_utc(2),
    )
    assert envelope.timestamp_normalized == _utc(0)
    assert envelope.timestamp_exchange == _utc(0)  # never overwritten by local receive time
    assert envelope.timestamp_provider == _utc(1)
    assert envelope.timestamp_received == _utc(2)
    assert envelope.latency_ms == pytest.approx(2000.0)


def test_build_envelope_falls_back_to_provider_then_received():
    only_provider = build_envelope(
        provider="databento", instrument="NQ", schema="trades", payload={},
        timestamp_provider=_utc(1), received_at=_utc(3),
    )
    assert only_provider.timestamp_normalized == _utc(1)
    assert only_provider.latency_ms == pytest.approx(2000.0)

    neither = build_envelope(provider="databento", instrument="NQ", schema="trades", payload={}, received_at=_utc(5))
    assert neither.timestamp_normalized == _utc(5)
    assert neither.latency_ms is None


def test_envelope_rejects_naive_datetimes():
    with pytest.raises(ValueError, match="timezone-aware"):
        LiveMessageEnvelope(
            timestamp_exchange=None, timestamp_provider=None,
            timestamp_received=dt.datetime(2024, 1, 1),  # naive
            timestamp_normalized=dt.datetime(2024, 1, 1),
            provider="databento", instrument="NQ", schema="trades", payload={},
        )


def test_recorder_counts_messages_via_injected_sink():
    recorded = []
    recorder = LiveRecorder(sink=recorded.append)
    envelope = build_envelope(provider="databento", instrument="NQ", schema="trades", payload={"price": 1.0})
    recorder.record(envelope)
    recorder.record(envelope)
    assert recorder.message_count == 2
    assert len(recorded) == 2


def test_recorder_rejects_both_sink_and_path():
    with pytest.raises(ValueError):
        LiveRecorder(sink=lambda e: None, path="ignored.jsonl")


def test_jsonl_sink_appends_one_line_per_message(tmp_path):
    path = tmp_path / "live" / "nq.jsonl"
    recorder = LiveRecorder(path=str(path))
    envelope = build_envelope(
        provider="databento", instrument="NQ", schema="trades", payload={"price": 100.25},
        timestamp_exchange=_utc(0),
    )
    recorder.record(envelope)
    recorder.record(envelope)

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["provider"] == "databento"
    assert record["instrument"] == "NQ"
    assert record["schema"] == "trades"
    assert record["payload"] == {"price": 100.25}
    assert record["timestamp_exchange"] is not None
