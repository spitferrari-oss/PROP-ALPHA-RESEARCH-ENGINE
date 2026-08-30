"""Dataset manifest (extension spec §9): every dataset written to the data
lake gets one of these — the record a future data-lineage query (extension
§63-64) ultimately resolves back to.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


def compute_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class DatasetManifest:
    id: str
    provider: str
    instrument: str
    venue: str
    start: str
    end: str
    timezone: str
    schema: str
    granularity: str
    created_at: str
    source_version: str
    sha256: str

    @classmethod
    def build(
        cls,
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
        path: str | Path,
        source_version: str = "unknown",
    ) -> "DatasetManifest":
        return cls(
            id=dataset_id,
            provider=provider,
            instrument=instrument,
            venue=venue,
            start=start.isoformat(),
            end=end.isoformat(),
            timezone=timezone,
            schema=schema,
            granularity=granularity,
            created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            source_version=source_version,
            sha256=compute_sha256(path),
        )

    def to_yaml(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.safe_dump({"dataset": asdict(self)}, f, sort_keys=False)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DatasetManifest":
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls(**raw["dataset"])
