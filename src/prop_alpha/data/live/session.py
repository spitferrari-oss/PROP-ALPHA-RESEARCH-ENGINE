"""Local recorder session orchestration (extension spec §14/§101, Phase F).

Phase C already built everything a live adapter needs to *support*
recording (`LiveRecorder`, the envelope/timestamp policy, `subscribe_live`
accepting an injected `recorder`); what was missing is something that
actually drives a bounded recording window against the data lake's `raw`
tier (Phase D) — this module is that missing piece, plus the `pae data
record` CLI command that wraps it.

`provider_factory` takes the `LiveRecorder` this function constructs (so
the caller doesn't have to know the output path ahead of time) and returns
a ready-to-subscribe `FuturesDataProvider` — e.g.
`lambda recorder: DatabentoProvider(recorder=recorder)`. This keeps
`record_live_session` itself provider-agnostic and fully testable with a
fake provider and an injected `sleep_fn`, with no real waiting or network
access (extension §134/§136).
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Callable

from prop_alpha.data.lake import DataLakePaths
from prop_alpha.data.live.recorder import LiveRecorder
from prop_alpha.data.recording_config import RecordingConfig
from prop_alpha.providers.base import DataLevel, FuturesDataProvider


@dataclass(frozen=True)
class RecordingSessionResult:
    instrument: str
    schema: str
    output_path: str
    message_count: int
    duration_seconds: float
    recorded: bool = True


def record_live_session(
    provider_factory: Callable[[LiveRecorder], FuturesDataProvider],
    provider_name: str,
    instrument: str,
    level: DataLevel,
    schema_for_path: str,
    lake: DataLakePaths,
    duration_seconds: float,
    config: RecordingConfig | None = None,
    date: dt.date | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> RecordingSessionResult:
    """Subscribes via `provider_factory`'s provider for `duration_seconds`,
    recording every message to `<lake>/raw/<provider_name>/<instrument>/
    <schema_for_path>/<date>.parquet`-adjacent JSONL (extension §11's
    partitioning, reused from Phase D), then closes the subscription.

    `config.enabled=False` is a legitimate no-op (extension §101) — no
    subscription is opened and no file is created.
    """
    config = config or RecordingConfig()
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive — a bounded recording window.")
    if not config.enabled:
        return RecordingSessionResult(
            instrument=instrument, schema=schema_for_path, output_path="",
            message_count=0, duration_seconds=0.0, recorded=False,
        )

    date = date or dt.datetime.now(dt.timezone.utc).date()
    lake.ensure()
    output_path = lake.partition_path("raw", provider_name, instrument, schema_for_path, date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    recorder = LiveRecorder(path=str(output_path))

    provider = provider_factory(recorder)
    handle = provider.subscribe_live(instrument, level, on_message=lambda raw: None)
    try:
        sleep_fn(duration_seconds)
    finally:
        handle.close()

    return RecordingSessionResult(
        instrument=instrument,
        schema=schema_for_path,
        output_path=str(output_path),
        message_count=recorder.message_count,
        duration_seconds=duration_seconds,
    )
