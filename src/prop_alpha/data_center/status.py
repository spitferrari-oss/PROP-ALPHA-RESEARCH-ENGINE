"""`DataCenterStatus` (extension §105-109): the single cross-market status
snapshot the dashboard renders. `assemble_data_center_status` is a pure
aggregator — every input is optional and independently `None`-able,
since a caller may have a live futures connection but no options feed
configured, a quality report but no market state yet, and so on. The
resulting `overall_status` is the worst severity found across whatever
inputs were actually supplied; a component that wasn't supplied
contributes no severity at all (never assumed healthy, never assumed
broken).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from prop_alpha.data.live.connection_manager import ConnectionState
from prop_alpha.data.live.health import FeedHealth
from prop_alpha.data.quality_config import DataQualityConfig
from prop_alpha.data.quality_engine import DataQualityReport
from prop_alpha.data_center.config import DataCenterConfig
from prop_alpha.options.gexbot.health import GexbotHealth
from prop_alpha.sync.config import SyncConfig

_STATUS_ORDER = ("UNKNOWN", "OK", "DEGRADED", "CRITICAL")

# Hardening pass (Step 34-35): the Data Center must say, in plain text,
# what kind of data it's actually showing — never let a mock/synthetic/
# replayed result render indistinguishably from a real live connection.
DATA_SOURCES = ("REAL", "REPLAY", "SYNTHETIC", "MOCK", "NOT_CONNECTED")


def _worse(current: str, candidate: str) -> str:
    return candidate if _STATUS_ORDER.index(candidate) > _STATUS_ORDER.index(current) else current


@dataclass(frozen=True)
class DataCenterStatus:
    timestamp: dt.datetime
    futures_feed: FeedHealth | None = None
    options_feed: GexbotHealth | None = None
    quality: DataQualityReport | None = None
    market_state_completeness: float | None = None
    sync_time_difference_ms: float | None = None
    overall_status: str = "UNKNOWN"
    issues: tuple[str, ...] = field(default_factory=tuple)
    data_source: str = "NOT_CONNECTED"


def assemble_data_center_status(
    timestamp: dt.datetime | None = None,
    futures_feed: FeedHealth | None = None,
    options_feed: GexbotHealth | None = None,
    quality: DataQualityReport | None = None,
    market_state_completeness: float | None = None,
    sync_time_difference_ms: float | None = None,
    quality_config: DataQualityConfig | None = None,
    sync_config: SyncConfig | None = None,
    data_center_config: DataCenterConfig | None = None,
    data_source: str = "NOT_CONNECTED",
) -> DataCenterStatus:
    if data_source not in DATA_SOURCES:
        raise ValueError(f"data_source must be one of {DATA_SOURCES}, got {data_source!r}")

    timestamp = timestamp or dt.datetime.now(dt.timezone.utc)
    quality_config = quality_config or DataQualityConfig()
    sync_config = sync_config or SyncConfig()
    data_center_config = data_center_config or DataCenterConfig()

    status = "UNKNOWN"
    issues: list[str] = []
    if data_source in ("MOCK", "SYNTHETIC", "REPLAY"):
        issues.append(f"data_source={data_source} — this status reflects {data_source.lower()} data, not a real live feed")

    if futures_feed is not None:
        status = _worse(status, "OK")
        if futures_feed.connection_state in (ConnectionState.DISCONNECTED, ConnectionState.FAILED):
            status = _worse(status, "CRITICAL")
            issues.append(f"futures feed connection_state={futures_feed.connection_state.value}")
        elif futures_feed.connection_state in (ConnectionState.RECONNECTING, ConnectionState.STALE):
            status = _worse(status, "DEGRADED")
            issues.append(f"futures feed connection_state={futures_feed.connection_state.value}")
        if (
            futures_feed.last_message_age_seconds is not None
            and futures_feed.last_message_age_seconds > quality_config.stale_thresholds.futures_seconds
        ):
            status = _worse(status, "DEGRADED")
            issues.append(
                f"futures feed last message {futures_feed.last_message_age_seconds:.1f}s old "
                f"(> {quality_config.stale_thresholds.futures_seconds}s threshold)"
            )
        if futures_feed.sequence_gaps > 0:
            status = _worse(status, "DEGRADED")
            issues.append(f"futures feed has {futures_feed.sequence_gaps} sequence gap(s)")

    if options_feed is not None:
        status = _worse(status, "OK")
        if not options_feed.connected or not options_feed.authenticated:
            status = _worse(status, "CRITICAL")
            issues.append(
                f"options feed connected={options_feed.connected} authenticated={options_feed.authenticated}"
            )
        if options_feed.error_rate > data_center_config.options_error_rate_warning:
            status = _worse(status, "DEGRADED")
            issues.append(
                f"options feed error_rate={options_feed.error_rate:.2%} "
                f"(> {data_center_config.options_error_rate_warning:.0%} threshold)"
            )
        if (
            options_feed.data_age_seconds is not None
            and options_feed.data_age_seconds > data_center_config.options_data_age_warning_seconds
        ):
            status = _worse(status, "DEGRADED")
            issues.append(
                f"options feed data {options_feed.data_age_seconds:.1f}s old "
                f"(> {data_center_config.options_data_age_warning_seconds}s threshold)"
            )
        if not options_feed.available_metrics:
            status = _worse(status, "DEGRADED")
            issues.append("options feed has no available metrics")

    if quality is not None:
        status = _worse(status, "OK")
        if quality.severity == "CRITICAL":
            status = _worse(status, "CRITICAL")
            issues.append(f"data quality score {quality.score:.1f} (CRITICAL)")
        elif quality.severity == "WARNING":
            status = _worse(status, "DEGRADED")
            issues.append(f"data quality score {quality.score:.1f} (WARNING)")

    if sync_time_difference_ms is not None:
        status = _worse(status, "OK")
        if sync_time_difference_ms > sync_config.max_time_difference_ms:
            status = _worse(status, "DEGRADED")
            issues.append(
                f"futures/options sync gap {sync_time_difference_ms:.1f}ms "
                f"(> {sync_config.max_time_difference_ms}ms tolerance)"
            )

    if market_state_completeness is not None:
        status = _worse(status, "OK")

    return DataCenterStatus(
        timestamp=timestamp,
        futures_feed=futures_feed,
        options_feed=options_feed,
        quality=quality,
        market_state_completeness=market_state_completeness,
        sync_time_difference_ms=sync_time_difference_ms,
        overall_status=status,
        issues=tuple(issues),
        data_source=data_source,
    )
