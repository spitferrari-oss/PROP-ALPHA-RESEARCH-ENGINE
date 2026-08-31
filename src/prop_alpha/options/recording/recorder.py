"""Immutable, append-only options snapshot recorder (hardening pass Step
27-28) — mirrors `data.live.recorder.LiveRecorder`'s exact pattern
(extension §7-8's immutability principle applies to options recordings
too: a written record is never overwritten, a correction is a new
record, never an in-place edit).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from prop_alpha.options.recording.collector import OptionsSnapshotRecord

_TIMESTAMP_FIELDS = ("timestamp_native", "timestamp_received", "timestamp_normalized")


def _jsonl_sink(path: str) -> Callable[[OptionsSnapshotRecord], None]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def sink(record: OptionsSnapshotRecord) -> None:
        payload = asdict(record)
        for key in _TIMESTAMP_FIELDS:
            if payload[key] is not None:
                payload[key] = payload[key].isoformat()
        with open(p, "a") as f:
            f.write(json.dumps(payload) + "\n")

    return sink


class OptionsRecorder:
    def __init__(
        self,
        sink: Callable[[OptionsSnapshotRecord], None] | None = None,
        path: str | None = None,
    ):
        if sink is not None and path is not None:
            raise ValueError("Pass either sink= or path=, not both.")
        if path is not None:
            sink = _jsonl_sink(path)
        self._sink = sink or (lambda record: None)
        self._count = 0

    def record(self, record: OptionsSnapshotRecord) -> None:
        self._sink(record)
        self._count += 1

    def record_many(self, records: list[OptionsSnapshotRecord]) -> None:
        for record in records:
            self.record(record)

    @property
    def record_count(self) -> int:
        return self._count
