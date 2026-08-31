"""Raw/normalized data immutability (extension spec §7-8): "Una volta
registrato: raw dataset, non deve essere modificato." Once a partition is
written, it is never overwritten — a correction produces version N+1: a
new file, a new manifest, a new append-only ledger entry, never a silent
rewrite.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from prop_alpha.data.manifest import DatasetManifest

LEDGER_FILENAME = "dataset_ledger.jsonl"


class DataImmutabilityError(RuntimeError):
    pass


def _record_manifest(path: Path, manifest: DatasetManifest, metadata_dir: Path) -> None:
    metadata_dir.mkdir(parents=True, exist_ok=True)
    with open(metadata_dir / LEDGER_FILENAME, "a") as f:
        f.write(json.dumps({"path": str(path), **asdict(manifest)}) + "\n")
    manifest.to_yaml(metadata_dir / f"{manifest.id}.yaml")


def next_version_path(path: str | Path) -> Path:
    """`.../2026-08-30.parquet` -> `.../2026-08-30.v2.parquet` -> `.v3...`
    — the caller asks for this explicitly to write a correction (extension
    §8); nothing here ever picks a version path automatically on write.
    """
    path = Path(path)
    if not path.exists():
        return path
    stem = path.stem.rsplit(".v", 1)[0] if ".v" in path.stem else path.stem
    version = 2
    while True:
        candidate = path.with_name(f"{stem}.v{version}{path.suffix}")
        if not candidate.exists():
            return candidate
        version += 1


def write_versioned_parquet(
    df: pd.DataFrame,
    path: str | Path,
    manifest: DatasetManifest,
    metadata_dir: str | Path,
) -> Path:
    """Writes `df` to `path`, raising `DataImmutabilityError` if that exact
    path already exists (use `next_version_path` first to get a
    correction's path), then appends `manifest` to the append-only
    dataset ledger and writes its own YAML file under `metadata_dir`.
    """
    path = Path(path)
    if path.exists():
        raise DataImmutabilityError(
            f"{path} already exists — raw/normalized data is immutable (extension §8). "
            f"Use next_version_path() to write a correction as a new version instead."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    _record_manifest(path, manifest, Path(metadata_dir))
    return path


def write_dataset(
    df: pd.DataFrame,
    path: str | Path,
    metadata_dir: str | Path,
    *,
    dataset_id: str,
    provider: str,
    instrument: str,
    venue: str,
    start: dt.date,
    end: dt.date,
    timezone: str,
    schema: str,
    granularity: str,
    source_version: str = "unknown",
) -> tuple[Path, DatasetManifest]:
    """Writes `df` to `path` (same write-once check and error as
    `write_versioned_parquet`), then builds the `DatasetManifest` from the
    file that was actually written. Unlike `write_versioned_parquet` —
    which requires a manifest, and therefore a file to hash, to already
    exist — this is the right entry point when there's no file yet to
    hash a manifest from, e.g. historical ingestion (Phase G): write
    first, then manifest the real bytes on disk, never a hash computed
    ahead of the write.
    """
    path = Path(path)
    if path.exists():
        raise DataImmutabilityError(
            f"{path} already exists — raw/normalized data is immutable (extension §8). "
            f"Use next_version_path() to write a correction as a new version instead."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)

    manifest = DatasetManifest.build(
        dataset_id=dataset_id, provider=provider, instrument=instrument, venue=venue,
        start=start, end=end, timezone=timezone, schema=schema, granularity=granularity,
        path=path, source_version=source_version,
    )
    _record_manifest(path, manifest, Path(metadata_dir))
    return path, manifest


def read_ledger(metadata_dir: str | Path) -> list[dict]:
    ledger_path = Path(metadata_dir) / LEDGER_FILENAME
    if not ledger_path.exists():
        return []
    with open(ledger_path) as f:
        return [json.loads(line) for line in f if line.strip()]
