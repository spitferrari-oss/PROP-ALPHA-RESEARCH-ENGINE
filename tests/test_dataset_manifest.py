import datetime as dt
import hashlib

from prop_alpha.data.manifest import DatasetManifest, compute_sha256


def test_compute_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"hello world")
    assert compute_sha256(path) == hashlib.sha256(b"hello world").hexdigest()


def test_build_populates_sha256_and_timestamps(tmp_path):
    path = tmp_path / "nq_trades.parquet"
    path.write_bytes(b"fake parquet bytes")

    manifest = DatasetManifest.build(
        dataset_id="ds-001", provider="databento", instrument="NQ", venue="GLBX.MDP3",
        start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 2), timezone="UTC",
        schema="trades", granularity="tick", path=path, source_version="v1",
    )
    assert manifest.sha256 == compute_sha256(path)
    assert manifest.start == "2024-01-01"
    assert manifest.end == "2024-01-02"
    assert manifest.created_at  # non-empty ISO timestamp


def test_to_yaml_and_from_yaml_round_trip(tmp_path):
    data_path = tmp_path / "nq_trades.parquet"
    data_path.write_bytes(b"fake parquet bytes")
    manifest = DatasetManifest.build(
        dataset_id="ds-002", provider="databento", instrument="NQ", venue="GLBX.MDP3",
        start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 2), timezone="UTC",
        schema="trades", granularity="tick", path=data_path,
    )
    manifest_path = tmp_path / "ds-002.yaml"
    manifest.to_yaml(manifest_path)

    loaded = DatasetManifest.from_yaml(manifest_path)
    assert loaded == manifest


def test_yaml_file_has_dataset_key_matching_spec_9(tmp_path):
    data_path = tmp_path / "d.parquet"
    data_path.write_bytes(b"x")
    manifest = DatasetManifest.build(
        dataset_id="ds-003", provider="databento", instrument="NQ", venue="GLBX.MDP3",
        start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 1), timezone="UTC",
        schema="ohlcv-1m", granularity="1m", path=data_path,
    )
    manifest_path = tmp_path / "ds-003.yaml"
    manifest.to_yaml(manifest_path)

    text = manifest_path.read_text()
    assert text.startswith("dataset:")
    for field_name in ("id", "provider", "instrument", "venue", "start", "end",
                        "timezone", "schema", "granularity", "created_at",
                        "source_version", "sha256"):
        assert f"{field_name}:" in text
