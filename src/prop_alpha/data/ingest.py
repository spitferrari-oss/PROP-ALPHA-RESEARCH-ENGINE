"""Historical ingestion orchestration (extension spec §10, Phase G):
incremental day-by-day download from a `FuturesDataProvider` into the data
lake's `raw` tier, with resume (skip already-ingested days), retries, and
Phase D/E's immutable-write + quality-gate discipline applied to every
partition.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from prop_alpha.data.immutable_store import write_dataset
from prop_alpha.data.lake import DataLakePaths
from prop_alpha.data.quality_config import DataQualityConfig
from prop_alpha.data.quality_engine import evaluate_batch_quality, is_blocked
from prop_alpha.providers.base import DataLevel, FuturesDataProvider


@dataclass(frozen=True)
class DayIngestResult:
    date: dt.date
    status: str  # "WRITTEN" | "SKIPPED_EXISTING" | "SKIPPED_EMPTY" | "FAILED"
    path: str | None = None
    quality_score: float | None = None
    quality_blocked: bool = False
    blocked_reasons: tuple[str, ...] = ()
    n_rows: int = 0
    error: str | None = None


@dataclass(frozen=True)
class IngestResult:
    days: list[DayIngestResult] = field(default_factory=list)

    @property
    def n_written(self) -> int:
        return sum(1 for d in self.days if d.status == "WRITTEN")

    @property
    def n_skipped_existing(self) -> int:
        return sum(1 for d in self.days if d.status == "SKIPPED_EXISTING")

    @property
    def n_failed(self) -> int:
        return sum(1 for d in self.days if d.status == "FAILED")

    @property
    def n_quality_blocked(self) -> int:
        return sum(1 for d in self.days if d.quality_blocked)


def _daterange(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def ingest_historical(
    provider: FuturesDataProvider,
    instrument: str,
    level: DataLevel,
    schema: str,
    start: dt.date,
    end: dt.date,
    lake: DataLakePaths,
    quality_config: DataQualityConfig | None = None,
    max_retries: int = 3,
    retry_backoff_seconds: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    expected_freq: pd.Timedelta | None = None,
) -> IngestResult:
    """Fetches `[start, end]` one day at a time (extension §10's
    incremental download), skipping any day whose raw partition already
    exists (resume — extension §7-8's immutability makes "already
    written" unambiguous), retrying a failed fetch up to `max_retries`
    times with linear backoff, and quality-gating each day's frame
    (Phase E) before writing it (Phase D's write-once store via
    `write_dataset`).

    A day whose quality score trips extension §103's `blocked_on` flags is
    still written — raw data is never silently dropped (§7) — but flagged
    `quality_blocked=True` with its `blocked_reasons`, so a caller decides
    what to do with it rather than this function silently discarding
    evidence of a bad feed day.

    Note: a day with no data at all (holiday/weekend) is `SKIPPED_EMPTY`
    and nothing is written for it — so a re-run currently re-fetches that
    day again rather than remembering it was checked. A marker for
    "checked, genuinely empty" would close that gap; not built yet.
    """
    quality_config = quality_config or DataQualityConfig()
    lake.ensure()
    results: list[DayIngestResult] = []

    for day in _daterange(start, end):
        existing_path = lake.partition_path("raw", provider.name, instrument, schema, day)
        if existing_path.exists():
            results.append(DayIngestResult(date=day, status="SKIPPED_EXISTING", path=str(existing_path)))
            continue

        df: pd.DataFrame | None = None
        error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                df = provider.get_historical(instrument, day, day, level, schema=schema)
                error = None
                break
            except Exception as exc:  # noqa: BLE001 - provider errors are arbitrary; retried, then reported
                error = str(exc)
                if attempt < max_retries:
                    sleep_fn(retry_backoff_seconds * attempt)

        if df is None:
            results.append(DayIngestResult(date=day, status="FAILED", error=error))
            continue

        if df.empty:
            results.append(DayIngestResult(date=day, status="SKIPPED_EMPTY"))
            continue

        quality_report = evaluate_batch_quality(df, expected_freq=expected_freq, expected_instrument=instrument)
        blocked, reasons = is_blocked(quality_report, quality_config)

        written_path, _manifest = write_dataset(
            df, existing_path, lake.metadata,
            dataset_id=f"{provider.name}-{instrument}-{schema}-{day.isoformat()}",
            provider=provider.name,
            instrument=instrument,
            venue=str(df.attrs.get("dataset", "unknown")),
            start=day, end=day, timezone="UTC",
            schema=schema, granularity=schema,
        )

        results.append(DayIngestResult(
            date=day, status="WRITTEN", path=str(written_path),
            quality_score=quality_report.score, quality_blocked=blocked,
            blocked_reasons=tuple(reasons), n_rows=len(df),
        ))

    return IngestResult(days=results)
