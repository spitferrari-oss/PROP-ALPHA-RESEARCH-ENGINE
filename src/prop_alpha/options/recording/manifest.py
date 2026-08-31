"""Manifest for a recorded options snapshot partition (hardening pass
Step 28) — mirrors `data.manifest.DatasetManifest`'s role and reuses its
`compute_sha256` helper rather than re-implementing hashing. Writing a
manifest to a path that already has one raises, matching the same
never-overwrite discipline `OptionsRecorder` and the futures data lake
already enforce.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from prop_alpha.data.manifest import compute_sha256


@dataclass(frozen=True)
class OptionsRecordingManifest:
    provider: str
    underlying: str
    date: str
    path: str
    sha256: str
    n_records: int
    recorded_at: str


def build_manifest(
    path: str | Path, provider: str, underlying: str, date: dt.date, n_records: int,
) -> OptionsRecordingManifest:
    path = Path(path)
    return OptionsRecordingManifest(
        provider=provider, underlying=underlying, date=date.isoformat(), path=str(path),
        sha256=compute_sha256(path), n_records=n_records,
        recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )


def write_manifest(manifest: OptionsRecordingManifest, metadata_dir: str | Path) -> Path:
    metadata_dir = Path(metadata_dir)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    out_path = metadata_dir / f"{manifest.provider}-{manifest.underlying}-{manifest.date}.json"
    if out_path.exists():
        raise FileExistsError(
            f"Manifest already exists at {out_path} — raw options recordings are immutable "
            f"(extension §7-8); write a new, distinct partition instead of overwriting."
        )
    out_path.write_text(json.dumps(asdict(manifest), indent=2))
    return out_path
