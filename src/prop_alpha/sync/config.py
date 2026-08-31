"""Futures/options synchronization tolerance (extension spec §35's own
worked example: `max_time_difference_ms: 500`). Kept out of the sync
module itself, following the same discipline as
`data.quality_config`/`data.recording_config`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyncConfig:
    max_time_difference_ms: float = 500.0
