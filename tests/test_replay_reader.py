import datetime as dt

import pandas as pd
import pytest

from prop_alpha.data.live.recorder import LiveRecorder, build_envelope
from prop_alpha.replay.reader import dataframe_to_envelopes, read_jsonl_envelopes

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def test_read_jsonl_envelopes_round_trips_recorded_session(tmp_path):
    path = tmp_path / "session.jsonl"
    recorder = LiveRecorder(path=str(path))
    envelope = build_envelope(
        provider="databento", instrument="ES", schema="ohlcv-1s", payload={"close": 4500.0},
        timestamp_exchange=_NOW, sequence=1, received_at=_NOW,
    )
    recorder.record(envelope)

    result = read_jsonl_envelopes(str(path))

    assert len(result) == 1
    got = result[0]
    assert got.provider == "databento"
    assert got.instrument == "ES"
    assert got.schema == "ohlcv-1s"
    assert got.payload == {"close": 4500.0}
    assert got.timestamp_exchange == _NOW
    assert got.timestamp_normalized == _NOW
    assert got.sequence == 1


def test_read_jsonl_envelopes_preserves_file_order_and_handles_multiple_lines(tmp_path):
    path = tmp_path / "session.jsonl"
    recorder = LiveRecorder(path=str(path))
    for i in range(3):
        recorder.record(build_envelope(
            provider="databento", instrument="ES", schema="ohlcv-1s", payload={"i": i},
            timestamp_exchange=_NOW + dt.timedelta(seconds=i), sequence=i,
        ))

    result = read_jsonl_envelopes(str(path))
    assert [e.payload["i"] for e in result] == [0, 1, 2]


def test_read_jsonl_envelopes_skips_blank_lines(tmp_path):
    path = tmp_path / "session.jsonl"
    recorder = LiveRecorder(path=str(path))
    recorder.record(build_envelope(
        provider="databento", instrument="ES", schema="ohlcv-1s", payload={}, timestamp_exchange=_NOW,
    ))
    with open(path, "a") as f:
        f.write("\n")

    result = read_jsonl_envelopes(str(path))
    assert len(result) == 1


def test_read_jsonl_envelopes_none_timestamp_provider_stays_none(tmp_path):
    path = tmp_path / "session.jsonl"
    recorder = LiveRecorder(path=str(path))
    recorder.record(build_envelope(
        provider="databento", instrument="ES", schema="ohlcv-1s", payload={}, timestamp_exchange=_NOW,
    ))
    result = read_jsonl_envelopes(str(path))
    assert result[0].timestamp_provider is None


def _bars_df():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31"], utc=True),
        "close": [4500.0, 4505.0],
        "volume": [100, 110],
    })


def test_dataframe_to_envelopes_builds_one_envelope_per_row():
    envelopes = dataframe_to_envelopes(_bars_df(), provider="databento", instrument="ES", schema="ohlcv-1m")
    assert len(envelopes) == 2
    assert envelopes[0].payload == {"close": 4500.0, "volume": 100}
    assert envelopes[0].provider == "databento"
    assert envelopes[0].sequence == 0
    assert envelopes[1].sequence == 1


def test_dataframe_to_envelopes_timestamp_fields_all_equal_bar_timestamp():
    envelopes = dataframe_to_envelopes(_bars_df(), provider="databento", instrument="ES", schema="ohlcv-1m")
    e = envelopes[0]
    assert e.timestamp_exchange == e.timestamp_received == e.timestamp_normalized
    assert e.timestamp_provider is None
    assert e.latency_ms is None


def test_dataframe_to_envelopes_missing_timestamp_column_raises():
    df = pd.DataFrame({"close": [1.0]})
    with pytest.raises(ValueError, match="timestamp"):
        dataframe_to_envelopes(df, provider="databento", instrument="ES", schema="ohlcv-1m")


def test_dataframe_to_envelopes_naive_timestamp_raises():
    df = pd.DataFrame({"timestamp": [dt.datetime(2024, 1, 2, 9, 30)], "close": [4500.0]})
    with pytest.raises(ValueError, match="timezone-naive"):
        dataframe_to_envelopes(df, provider="databento", instrument="ES", schema="ohlcv-1m")


def test_dataframe_to_envelopes_empty_frame_returns_empty_list():
    df = pd.DataFrame({"timestamp": pd.to_datetime([], utc=True), "close": []})
    assert dataframe_to_envelopes(df, provider="databento", instrument="ES", schema="ohlcv-1m") == []
