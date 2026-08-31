"""Data Center status thresholds not already owned by another config —
kept out of `status.py` itself, following the same discipline as
`data.quality_config`/`sync.config`. Futures feed staleness already has a
threshold (`data.quality_config.StaleThresholds.futures_seconds`) and
sync tolerance already has one (`sync.config.SyncConfig.
max_time_difference_ms`); this only adds the two GEXBOT-health
thresholds nothing else in the codebase owns yet.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataCenterConfig:
    options_error_rate_warning: float = 0.1
    options_data_age_warning_seconds: float = 120.0
