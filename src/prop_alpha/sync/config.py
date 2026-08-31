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
    # Hardening pass (Step 30): beyond this age, a matched options
    # snapshot is stale even though it fell within max_time_difference_ms
    # of the futures bar it was paired with — the two are different
    # questions ("was there a close-enough snapshot at all" vs. "is that
    # snapshot's own data still fresh"). Configurable, never hardcoded in
    # cross_market.py itself.
    max_freshness_seconds: float = 60.0
