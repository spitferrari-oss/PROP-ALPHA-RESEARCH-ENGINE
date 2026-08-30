"""Historical data lake directory structure (extension spec §6, §11):
raw -> normalized -> curated -> features -> outcomes -> snapshots ->
metadata, each partitioned by provider/instrument/schema/date.

This is separate from — and layered on top of — the core research
pipeline's own `data/raw`/`data/features` used by the synthetic-data
backtester (Phases 1-10): that pipeline stays untouched. `DataLakePaths`
is infrastructure for the real-provider ingestion pipeline this extension
adds, defaulting to its own `data/lake/` root so the two never collide.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

TIERS = ("raw", "normalized", "curated", "features", "outcomes", "snapshots", "metadata")


@dataclass(frozen=True)
class DataLakePaths:
    root: Path = field(default_factory=lambda: Path("data/lake"))

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root))

    def tier(self, name: str) -> Path:
        if name not in TIERS:
            raise ValueError(f"Unknown data lake tier '{name}' — must be one of {TIERS}")
        return self.root / name

    @property
    def raw(self) -> Path:
        return self.tier("raw")

    @property
    def normalized(self) -> Path:
        return self.tier("normalized")

    @property
    def curated(self) -> Path:
        return self.tier("curated")

    @property
    def features(self) -> Path:
        return self.tier("features")

    @property
    def outcomes(self) -> Path:
        return self.tier("outcomes")

    @property
    def snapshots(self) -> Path:
        return self.tier("snapshots")

    @property
    def metadata(self) -> Path:
        return self.tier("metadata")

    def ensure(self) -> None:
        for name in TIERS:
            self.tier(name).mkdir(parents=True, exist_ok=True)

    def partition_path(
        self,
        tier: str,
        provider: str,
        instrument: str,
        schema: str,
        date: dt.date,
    ) -> Path:
        """extension §11's partitioning example generalized across every
        tier: `data/<tier>/<provider>/<instrument>/<schema>/<date>.parquet`
        (e.g. `data/raw/databento/NQ/trades/2026-08-30.parquet`).
        """
        return self.tier(tier) / provider / instrument / schema / f"{date.isoformat()}.parquet"
