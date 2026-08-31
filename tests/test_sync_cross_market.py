import datetime as dt

import pandas as pd
import pytest

from prop_alpha.options.gexbot.parser import parse_snapshot
from prop_alpha.options.normalize import normalize_gex_snapshot
from prop_alpha.sync.config import SyncConfig
from prop_alpha.sync.cross_market import find_nearest_snapshot, synchronize_frame, synchronize_snapshot


def _ts(seconds_offset: float = 0.0, base=None):
    base = base or dt.datetime(2024, 1, 2, 15, 31, 0, tzinfo=dt.timezone.utc)
    return base + dt.timedelta(seconds=seconds_offset)


def _snapshot(ts, gex=1.0e9, spot=4500.0):
    gex_snapshot = parse_snapshot({"gex": gex, "spot": spot}, "SPX", received_at=ts)
    return normalize_gex_snapshot(gex_snapshot, timestamp=ts)


def _futures_df(timestamps):
    return pd.DataFrame({"timestamp": timestamps, "close": [100.0 + i for i in range(len(timestamps))]})


def test_find_nearest_snapshot_picks_closest_within_tolerance():
    target = _ts(2.0)
    snapshots = [_snapshot(_ts(0.0)), _snapshot(_ts(2.1)), _snapshot(_ts(5.0))]
    nearest, diff_ms = find_nearest_snapshot(target, snapshots, SyncConfig(max_time_difference_ms=500))
    assert nearest is snapshots[1]
    assert diff_ms == pytest.approx(100.0)


def test_find_nearest_snapshot_returns_none_when_outside_tolerance():
    nearest, diff_ms = find_nearest_snapshot(_ts(0.0), [_snapshot(_ts(2.0))], SyncConfig(max_time_difference_ms=500))
    assert nearest is None
    assert diff_ms is None


def test_find_nearest_snapshot_empty_list_returns_none():
    nearest, diff_ms = find_nearest_snapshot(_ts(), [], SyncConfig())
    assert nearest is None
    assert diff_ms is None


def test_find_nearest_snapshot_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        find_nearest_snapshot(dt.datetime(2024, 1, 1), [_snapshot(_ts())], SyncConfig())


def test_synchronize_snapshot_pairs_futures_bar_with_nearest_options():
    futures_bar = {"close": 4500.25, "regime_rule": "TREND_UP"}
    snapshots = [_snapshot(_ts(0.1))]
    state = synchronize_snapshot(futures_bar, _ts(0.0), snapshots, SyncConfig(max_time_difference_ms=500))
    assert state.options is snapshots[0]
    assert state.regime == "TREND_UP"
    assert state.futures == futures_bar
    assert state.sync_time_difference_ms == pytest.approx(100.0)
    assert state.market_state is None  # Phase L, not built yet


def test_synchronize_snapshot_options_none_when_no_match():
    state = synchronize_snapshot({"close": 4500.25}, _ts(0.0), [_snapshot(_ts(5.0))], SyncConfig(max_time_difference_ms=500))
    assert state.options is None
    assert state.sync_time_difference_ms is None


def test_synchronize_snapshot_regime_none_when_absent_from_futures_bar():
    state = synchronize_snapshot({"close": 1.0}, _ts(), [], SyncConfig())
    assert state.regime is None


def test_synchronize_frame_matches_within_tolerance_and_leaves_nan_outside_it():
    futures_df = _futures_df([_ts(0.0), _ts(10.0), _ts(20.0)])
    snapshots = [_snapshot(_ts(0.05), gex=1.0e9), _snapshot(_ts(10.4), gex=2.0e9), _snapshot(_ts(100.0), gex=3.0e9)]

    result = synchronize_frame(futures_df, snapshots, SyncConfig(max_time_difference_ms=500))

    assert result.loc[0, "options_gex"] == 1.0e9
    assert result.loc[1, "options_gex"] == 2.0e9
    assert pd.isna(result.loc[2, "options_gex"])  # nearest snapshot is 80s away, outside 500ms tolerance


def test_synchronize_frame_missing_timestamp_column_raises():
    with pytest.raises(ValueError, match="'timestamp' column not found"):
        synchronize_frame(pd.DataFrame({"close": [1.0]}), [], timestamp_column="timestamp")


def test_synchronize_frame_no_snapshots_returns_all_nan_options_columns():
    result = synchronize_frame(_futures_df([_ts(0.0)]), [])
    assert pd.isna(result.loc[0, "options_gex"])
    assert pd.isna(result.loc[0, "sync_time_difference_ms"])


def test_synchronize_frame_reports_time_difference_in_ms():
    result = synchronize_frame(_futures_df([_ts(0.0)]), [_snapshot(_ts(0.25))], SyncConfig(max_time_difference_ms=1000))
    assert result.loc[0, "sync_time_difference_ms"] == pytest.approx(250.0)


# --- hardening pass: sync_quality / freshness_seconds / data_quality (Step 29-31) ---

def test_synchronize_snapshot_no_match_reports_sync_quality_no_match():
    state = synchronize_snapshot({}, _ts(0.0), [], SyncConfig(max_time_difference_ms=500))
    assert state.sync_quality == "NO_MATCH"
    assert state.freshness_seconds is None
    assert state.options is None


def test_synchronize_snapshot_fresh_match_reports_synced():
    state = synchronize_snapshot(
        {}, _ts(0.0), [_snapshot(_ts(0.1))],
        SyncConfig(max_time_difference_ms=500, max_freshness_seconds=60.0),
    )
    assert state.sync_quality == "SYNCED"
    assert state.freshness_seconds == pytest.approx(0.1)


def test_synchronize_snapshot_matched_but_old_reports_stale():
    # within max_time_difference_ms (so it's still the "nearest match")
    # but beyond max_freshness_seconds -- a real scenario when the sync
    # tolerance is loose but the caller wants a tighter freshness bar.
    state = synchronize_snapshot(
        {}, _ts(0.0), [_snapshot(_ts(90.0))],
        SyncConfig(max_time_difference_ms=120_000, max_freshness_seconds=60.0),
    )
    assert state.sync_quality == "STALE"
    assert state.freshness_seconds == pytest.approx(90.0)


def test_synchronize_snapshot_data_quality_is_passthrough_not_computed():
    state = synchronize_snapshot({}, _ts(0.0), [], data_quality=97.5)
    assert state.data_quality == 97.5


def test_synchronize_snapshot_data_quality_defaults_to_none():
    state = synchronize_snapshot({}, _ts(0.0), [])
    assert state.data_quality is None
