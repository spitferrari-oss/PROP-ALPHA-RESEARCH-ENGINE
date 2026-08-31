import datetime as dt

import pytest

from prop_alpha.data.live.connection_manager import ConnectionState
from prop_alpha.data.live.health import FeedHealth
from prop_alpha.data.quality_engine import CheckResult, DataQualityReport
from prop_alpha.data_center.status import assemble_data_center_status
from prop_alpha.options.gexbot.health import GexbotHealth

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _feed_health(**overrides) -> FeedHealth:
    fields = dict(
        provider="databento", instrument="ES", connection_state=ConnectionState.CONNECTED,
        messages_received=100, messages_per_second=10.0, sequence_gaps=0, last_message_age_seconds=0.5,
    )
    fields.update(overrides)
    return FeedHealth(**fields)


def _options_health(**overrides) -> GexbotHealth:
    fields = dict(
        connected=True, authenticated=True, last_update=_NOW, latency_ms=50.0,
        error_rate=0.0, data_age_seconds=5.0, available_metrics=("gex", "dex"),
    )
    fields.update(overrides)
    return GexbotHealth(**fields)


def test_no_inputs_yields_unknown_status_and_no_issues():
    status = assemble_data_center_status(timestamp=_NOW)
    assert status.overall_status == "UNKNOWN"
    assert status.issues == ()


def test_all_healthy_inputs_yield_ok():
    status = assemble_data_center_status(
        timestamp=_NOW,
        futures_feed=_feed_health(),
        options_feed=_options_health(),
        quality=DataQualityReport(score=100.0, severity="EXCELLENT"),
        market_state_completeness=1.0,
        sync_time_difference_ms=100.0,
    )
    assert status.overall_status == "OK"
    assert status.issues == ()


def test_futures_disconnected_is_critical():
    status = assemble_data_center_status(
        timestamp=_NOW, futures_feed=_feed_health(connection_state=ConnectionState.DISCONNECTED),
    )
    assert status.overall_status == "CRITICAL"
    assert any("connection_state=DISCONNECTED" in issue for issue in status.issues)


def test_futures_reconnecting_is_degraded_not_critical():
    status = assemble_data_center_status(
        timestamp=_NOW, futures_feed=_feed_health(connection_state=ConnectionState.RECONNECTING),
    )
    assert status.overall_status == "DEGRADED"


def test_futures_stale_message_age_is_degraded():
    status = assemble_data_center_status(timestamp=_NOW, futures_feed=_feed_health(last_message_age_seconds=30.0))
    assert status.overall_status == "DEGRADED"
    assert any("last message" in issue for issue in status.issues)


def test_futures_sequence_gaps_is_degraded():
    status = assemble_data_center_status(timestamp=_NOW, futures_feed=_feed_health(sequence_gaps=3))
    assert status.overall_status == "DEGRADED"
    assert any("sequence gap" in issue for issue in status.issues)


def test_options_not_authenticated_is_critical():
    status = assemble_data_center_status(timestamp=_NOW, options_feed=_options_health(authenticated=False))
    assert status.overall_status == "CRITICAL"


def test_options_high_error_rate_is_degraded():
    status = assemble_data_center_status(timestamp=_NOW, options_feed=_options_health(error_rate=0.5))
    assert status.overall_status == "DEGRADED"


def test_options_no_available_metrics_is_degraded():
    status = assemble_data_center_status(timestamp=_NOW, options_feed=_options_health(available_metrics=()))
    assert status.overall_status == "DEGRADED"


def test_quality_critical_severity_is_critical():
    report = DataQualityReport(
        checks=[CheckResult(name="invalid_prices", n_checked=100, n_violations=50)],
        score=50.0, severity="CRITICAL",
    )
    status = assemble_data_center_status(timestamp=_NOW, quality=report)
    assert status.overall_status == "CRITICAL"


def test_quality_warning_severity_is_degraded():
    status = assemble_data_center_status(
        timestamp=_NOW, quality=DataQualityReport(score=96.0, severity="WARNING"),
    )
    assert status.overall_status == "DEGRADED"


def test_sync_gap_beyond_tolerance_is_degraded():
    status = assemble_data_center_status(timestamp=_NOW, sync_time_difference_ms=1000.0)
    assert status.overall_status == "DEGRADED"


def test_sync_gap_within_tolerance_is_ok():
    status = assemble_data_center_status(timestamp=_NOW, sync_time_difference_ms=100.0)
    assert status.overall_status == "OK"


def test_worst_status_wins_across_multiple_inputs():
    status = assemble_data_center_status(
        timestamp=_NOW,
        futures_feed=_feed_health(),  # OK
        options_feed=_options_health(authenticated=False),  # CRITICAL
    )
    assert status.overall_status == "CRITICAL"


def test_timestamp_defaults_to_now_when_omitted():
    status = assemble_data_center_status()
    assert status.timestamp.tzinfo is not None


# --- hardening pass: data_source labeling (Step 34-35) ---

def test_data_source_defaults_to_not_connected():
    status = assemble_data_center_status(timestamp=_NOW)
    assert status.data_source == "NOT_CONNECTED"


def test_data_source_real_adds_no_issue():
    status = assemble_data_center_status(timestamp=_NOW, data_source="REAL")
    assert status.data_source == "REAL"
    assert status.issues == ()


def test_data_source_mock_adds_a_visible_issue():
    status = assemble_data_center_status(timestamp=_NOW, data_source="MOCK")
    assert status.data_source == "MOCK"
    assert any("data_source=MOCK" in issue for issue in status.issues)


def test_data_source_synthetic_and_replay_also_flagged():
    for source in ("SYNTHETIC", "REPLAY"):
        status = assemble_data_center_status(timestamp=_NOW, data_source=source)
        assert any(f"data_source={source}" in issue for issue in status.issues)


def test_data_source_invalid_value_raises():
    with pytest.raises(ValueError, match="data_source"):
        assemble_data_center_status(timestamp=_NOW, data_source="FAKE_NEWS")
