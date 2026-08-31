"""Futures/options synchronization (extension spec §35-36): aligns a
futures bar/timestamp against the nearest options snapshot on a common
UTC time axis, within a configurable tolerance — never fabricating a
pairing when nothing is close enough. Extension §35's own worked example:

    15:31:02.100 Futures
    15:31:02.120 Options
    sync: max_time_difference_ms: 500

`CrossMarketState` (§36) is the output shape. Its `market_state` field
(the full `MarketState_t` vector) is Phase L's job, not built yet — it
stays `None` here rather than a fabricated partial vector. `regime` is
passed through from whatever the futures bar's own already-computed
`regime_rule` column says (the core Regime Engine, Phases 1-10), not
re-derived here.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from prop_alpha.options.models import OptionsSnapshot
from prop_alpha.sync.config import SyncConfig

_OPTIONS_MERGE_COLUMNS = (
    "spot", "gex", "dex", "gamma_flip", "major_positive_gamma", "major_negative_gamma",
    "vanna", "charm", "vomma", "skew", "options_volume", "open_interest",
)


@dataclass(frozen=True)
class CrossMarketState:
    timestamp: dt.datetime
    futures: dict
    options: OptionsSnapshot | None
    sync_time_difference_ms: float | None
    market_state: dict | None = None
    regime: str | None = None
    # Hardening pass (Step 29-31): explicit sync/freshness/quality labels
    # on the pairing itself, distinct from any per-metric availability
    # already carried on `options` (Phase I's OptionsSnapshot). `None`
    # values here mean "not evaluated," never a fabricated "healthy."
    sync_quality: str | None = None       # "SYNCED" | "NO_MATCH" | "STALE"
    freshness_seconds: float | None = None  # age of `options`, if any, relative to `timestamp`
    data_quality: float | None = None      # pass-through slot for a caller's own DataQualityReport.score


def _as_utc(ts) -> dt.datetime:
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    if ts.tzinfo is None:
        raise ValueError("Futures/options timestamps must be timezone-aware UTC (extension §16/§17).")
    return ts


def find_nearest_snapshot(
    target_timestamp,
    options_snapshots: list[OptionsSnapshot],
    config: SyncConfig | None = None,
) -> tuple[OptionsSnapshot | None, float | None]:
    """Nearest-neighbor search over `options_snapshots` by absolute time
    distance from `target_timestamp`. Returns `(None, None)` when nothing
    is within `config.max_time_difference_ms` — extension §35 says
    associate data *within a window*, not unconditionally.
    """
    config = config or SyncConfig()
    target_timestamp = _as_utc(target_timestamp)
    if not options_snapshots:
        return None, None

    best = min(
        options_snapshots,
        key=lambda snap: abs((_as_utc(snap.timestamp) - target_timestamp).total_seconds()),
    )
    diff_ms = abs((_as_utc(best.timestamp) - target_timestamp).total_seconds()) * 1000.0
    if diff_ms > config.max_time_difference_ms:
        return None, None
    return best, diff_ms


def synchronize_snapshot(
    futures_bar: dict,
    futures_timestamp,
    options_snapshots: list[OptionsSnapshot],
    config: SyncConfig | None = None,
    data_quality: float | None = None,
) -> CrossMarketState:
    """Pairs one futures bar with the nearest options snapshot — the
    online/live shape (Phase O's shadow mode: "what's the freshest
    options context for the bar that just closed").

    `sync_quality` (hardening pass Step 29-31) is derived, never
    fabricated: `"NO_MATCH"` when no snapshot fell within `config.
    max_time_difference_ms` (`options` is `None`), `"STALE"` when a match
    was found but its age exceeds `config.max_freshness_seconds`,
    `"SYNCED"` otherwise. `data_quality` is a pass-through slot — this
    function doesn't compute one itself (that's `data.quality_engine`'s
    job on the futures side), it only carries whatever score a caller
    already has alongside the pairing.
    """
    config = config or SyncConfig()
    options, diff_ms = find_nearest_snapshot(futures_timestamp, options_snapshots, config)
    freshness_seconds = diff_ms / 1000.0 if diff_ms is not None else None

    if options is None:
        sync_quality = "NO_MATCH"
    elif freshness_seconds is not None and freshness_seconds > config.max_freshness_seconds:
        sync_quality = "STALE"
    else:
        sync_quality = "SYNCED"

    return CrossMarketState(
        timestamp=_as_utc(futures_timestamp),
        futures=futures_bar,
        options=options,
        sync_time_difference_ms=diff_ms,
        regime=futures_bar.get("regime_rule"),
        sync_quality=sync_quality,
        freshness_seconds=freshness_seconds,
        data_quality=data_quality,
    )


def synchronize_frame(
    futures_df: pd.DataFrame,
    options_snapshots: list[OptionsSnapshot],
    config: SyncConfig | None = None,
    timestamp_column: str = "timestamp",
) -> pd.DataFrame:
    """Vectorized nearest-neighbor join of `futures_df` against
    `options_snapshots`, via `pandas.merge_asof` — the standard "as-of"
    join for exactly this nearest-timestamp-within-tolerance pairing. The
    historical/research shape (Phase K's conditional-EV-by-options-state
    work needs a whole synced series, not one pairing at a time). A
    futures row with no options snapshot within tolerance gets `NaN` in
    the `options_*` columns, not a fabricated pairing.
    """
    config = config or SyncConfig()
    if timestamp_column not in futures_df.columns:
        raise ValueError(f"synchronize_frame: '{timestamp_column}' column not found in futures_df.")

    left = futures_df.sort_values(timestamp_column).reset_index(drop=True)
    option_cols = [f"options_{name}" for name in _OPTIONS_MERGE_COLUMNS]

    if not options_snapshots:
        result = left.copy()
        for col in option_cols:
            result[col] = float("nan")
        result["sync_time_difference_ms"] = float("nan")
        return result

    rows = []
    for snap in options_snapshots:
        row = {"options_timestamp": _as_utc(snap.timestamp)}
        for name in _OPTIONS_MERGE_COLUMNS:
            row[f"options_{name}"] = getattr(snap, name).value
        rows.append(row)
    right = pd.DataFrame(rows).sort_values("options_timestamp").reset_index(drop=True)

    merged = pd.merge_asof(
        left, right, left_on=timestamp_column, right_on="options_timestamp",
        direction="nearest", tolerance=pd.Timedelta(milliseconds=config.max_time_difference_ms),
    )
    merged["sync_time_difference_ms"] = (
        (merged[timestamp_column] - merged["options_timestamp"]).abs().dt.total_seconds() * 1000.0
    )
    return merged
