import datetime as dt
import json

import pytest

from prop_alpha.options.models import AvailabilityStatus, Metric, MetricAvailability, OptionsSnapshot
from prop_alpha.options.recording.collector import collect_snapshot_records
from prop_alpha.options.recording.manifest import build_manifest, write_manifest
from prop_alpha.options.recording.recorder import OptionsRecorder

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _metric(value, status=AvailabilityStatus.AVAILABLE, timestamp=_NOW, freshness=1.0) -> Metric:
    return Metric(value=value, availability=MetricAvailability(
        status=status, timestamp=timestamp, source="gexbot", freshness_seconds=freshness,
    ))


def _snapshot() -> OptionsSnapshot:
    return OptionsSnapshot(
        timestamp=_NOW, underlying="SPX",
        spot=_metric(4500.0), gex=_metric(1.5e9), dex=_metric(2.0e8), gamma_flip=_metric(4490.0),
        major_positive_gamma=_metric(4550.0), major_negative_gamma=_metric(4450.0),
        vanna=_metric(None, AvailabilityStatus.UNAVAILABLE, timestamp=None, freshness=None),
        charm=_metric(None, AvailabilityStatus.UNAVAILABLE, timestamp=None, freshness=None),
        vomma=_metric(None, AvailabilityStatus.UNAVAILABLE, timestamp=None, freshness=None),
        skew=_metric(0.1), options_volume=_metric(100000), open_interest=_metric(500000),
    )


def test_collect_snapshot_records_one_per_metric():
    records = collect_snapshot_records(_snapshot(), provider="gexbot", received_at=_NOW)
    assert len(records) == 12
    assert {r.metric for r in records} == {
        "spot", "gex", "dex", "gamma_flip", "major_positive_gamma", "major_negative_gamma",
        "vanna", "charm", "vomma", "skew", "options_volume", "open_interest",
    }


def test_collect_snapshot_records_preserves_per_metric_availability():
    records = collect_snapshot_records(_snapshot(), provider="gexbot", received_at=_NOW)
    by_metric = {r.metric: r for r in records}
    assert by_metric["gex"].availability == "AVAILABLE"
    assert by_metric["gex"].value == 1.5e9
    assert by_metric["vanna"].availability == "UNAVAILABLE"
    assert by_metric["vanna"].value is None  # missing != zero


def test_collect_snapshot_records_naive_received_at_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        collect_snapshot_records(_snapshot(), provider="gexbot", received_at=dt.datetime(2024, 1, 2))


def test_collect_snapshot_records_defaults_received_at_to_now():
    records = collect_snapshot_records(_snapshot(), provider="gexbot")
    assert records[0].timestamp_received.tzinfo is not None


def test_recorder_writes_jsonl_and_counts(tmp_path):
    path = tmp_path / "spx.jsonl"
    recorder = OptionsRecorder(path=str(path))
    records = collect_snapshot_records(_snapshot(), provider="gexbot", received_at=_NOW)
    recorder.record_many(records)

    assert recorder.record_count == 12
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 12
    first = json.loads(lines[0])
    assert first["provider"] == "gexbot"
    assert first["underlying"] == "SPX"
    assert isinstance(first["timestamp_received"], str)


def test_recorder_is_append_only_across_instances(tmp_path):
    path = tmp_path / "spx.jsonl"
    records = collect_snapshot_records(_snapshot(), provider="gexbot", received_at=_NOW)
    OptionsRecorder(path=str(path)).record_many(records)
    OptionsRecorder(path=str(path)).record_many(records)
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 24


def test_recorder_rejects_both_sink_and_path():
    with pytest.raises(ValueError, match="either"):
        OptionsRecorder(sink=lambda r: None, path="x.jsonl")


def test_build_and_write_manifest(tmp_path):
    path = tmp_path / "spx.jsonl"
    recorder = OptionsRecorder(path=str(path))
    records = collect_snapshot_records(_snapshot(), provider="gexbot", received_at=_NOW)
    recorder.record_many(records)

    manifest = build_manifest(path, provider="gexbot", underlying="SPX", date=dt.date(2024, 1, 2), n_records=12)
    assert manifest.n_records == 12
    assert len(manifest.sha256) == 64

    metadata_dir = tmp_path / "metadata"
    out_path = write_manifest(manifest, metadata_dir)
    assert out_path.exists()
    written = json.loads(out_path.read_text())
    assert written["provider"] == "gexbot"


def test_write_manifest_refuses_to_overwrite(tmp_path):
    path = tmp_path / "spx.jsonl"
    OptionsRecorder(path=str(path)).record_many(
        collect_snapshot_records(_snapshot(), provider="gexbot", received_at=_NOW)
    )
    manifest = build_manifest(path, provider="gexbot", underlying="SPX", date=dt.date(2024, 1, 2), n_records=12)
    metadata_dir = tmp_path / "metadata"
    write_manifest(manifest, metadata_dir)
    with pytest.raises(FileExistsError, match="immutable"):
        write_manifest(manifest, metadata_dir)
