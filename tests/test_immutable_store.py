import datetime as dt

import pandas as pd
import pytest

from prop_alpha.data.immutable_store import (
    DataImmutabilityError,
    next_version_path,
    read_ledger,
    write_dataset,
    write_versioned_parquet,
)
from prop_alpha.data.manifest import DatasetManifest, compute_sha256


def test_write_versioned_parquet_creates_file_manifest_and_ledger_entry(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3]})
    path = tmp_path / "raw" / "2024-01-01.parquet"
    metadata_dir = tmp_path / "metadata"

    # sha256 needs the file to exist first for DatasetManifest.build, so
    # write once via to_parquet directly just to hash it, then rely on the
    # store's own write for the real assertion.
    path.parent.mkdir(parents=True)
    df.to_parquet(path, index=False)
    manifest = DatasetManifest.build(
        dataset_id="ds-1", provider="databento", instrument="NQ", venue="GLBX.MDP3",
        start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 1), timezone="UTC",
        schema="ohlcv-1m", granularity="1m", path=path,
    )
    path.unlink()  # let write_versioned_parquet do the real, checked write

    written_path = write_versioned_parquet(df, path, manifest, metadata_dir)
    assert written_path == path
    assert path.exists()
    assert (metadata_dir / "ds-1.yaml").exists()

    ledger = read_ledger(metadata_dir)
    assert len(ledger) == 1
    assert ledger[0]["path"] == str(path)
    assert ledger[0]["id"] == "ds-1"


def test_write_versioned_parquet_refuses_overwrite(tmp_path):
    df = pd.DataFrame({"a": [1]})
    path = tmp_path / "raw" / "2024-01-01.parquet"
    metadata_dir = tmp_path / "metadata"
    path.parent.mkdir(parents=True)
    df.to_parquet(path, index=False)
    manifest = DatasetManifest.build(
        dataset_id="ds-2", provider="databento", instrument="NQ", venue="GLBX.MDP3",
        start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 1), timezone="UTC",
        schema="ohlcv-1m", granularity="1m", path=path,
    )

    with pytest.raises(DataImmutabilityError):
        write_versioned_parquet(df, path, manifest, metadata_dir)


def test_ledger_is_append_only_across_multiple_writes(tmp_path):
    metadata_dir = tmp_path / "metadata"
    for i, day in enumerate(["2024-01-01", "2024-01-02"], start=1):
        df = pd.DataFrame({"a": [i]})
        path = tmp_path / "raw" / f"{day}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
        manifest = DatasetManifest.build(
            dataset_id=f"ds-{i}", provider="databento", instrument="NQ", venue="GLBX.MDP3",
            start=dt.date(2024, 1, i), end=dt.date(2024, 1, i), timezone="UTC",
            schema="ohlcv-1m", granularity="1m", path=path,
        )
        path.unlink()
        write_versioned_parquet(df, path, manifest, metadata_dir)

    ledger = read_ledger(metadata_dir)
    assert len(ledger) == 2
    assert [entry["id"] for entry in ledger] == ["ds-1", "ds-2"]


def test_next_version_path_increments_when_file_exists(tmp_path):
    path = tmp_path / "2024-01-01.parquet"
    assert next_version_path(path) == path  # doesn't exist yet -> same path

    path.write_bytes(b"v1")
    v2 = next_version_path(path)
    assert v2.name == "2024-01-01.v2.parquet"

    v2.write_bytes(b"v2")
    v3 = next_version_path(path)
    assert v3.name == "2024-01-01.v3.parquet"


def test_read_ledger_on_missing_file_returns_empty_list(tmp_path):
    assert read_ledger(tmp_path / "does_not_exist") == []


def test_write_dataset_writes_file_and_manifest_from_actual_bytes(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3]})
    path = tmp_path / "raw" / "2024-01-01.parquet"
    metadata_dir = tmp_path / "metadata"

    written_path, manifest = write_dataset(
        df, path, metadata_dir,
        dataset_id="ds-ingest-1", provider="databento", instrument="NQ", venue="GLBX.MDP3",
        start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 1), timezone="UTC",
        schema="ohlcv-1m", granularity="1m",
    )

    assert written_path == path
    assert path.exists()
    assert manifest.sha256 == compute_sha256(path)  # hashed from the real written bytes
    assert (metadata_dir / "ds-ingest-1.yaml").exists()
    ledger = read_ledger(metadata_dir)
    assert ledger[0]["id"] == "ds-ingest-1"


def test_write_dataset_refuses_overwrite(tmp_path):
    df = pd.DataFrame({"a": [1]})
    path = tmp_path / "raw" / "2024-01-01.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"already here")

    with pytest.raises(DataImmutabilityError):
        write_dataset(
            df, path, tmp_path / "metadata",
            dataset_id="ds-ingest-2", provider="databento", instrument="NQ", venue="GLBX.MDP3",
            start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 1), timezone="UTC",
            schema="ohlcv-1m", granularity="1m",
        )
