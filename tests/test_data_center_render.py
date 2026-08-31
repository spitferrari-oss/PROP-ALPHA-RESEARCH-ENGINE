import datetime as dt

from prop_alpha.data.live.connection_manager import ConnectionState
from prop_alpha.data.live.health import FeedHealth
from prop_alpha.data.quality_engine import CheckResult, DataQualityReport
from prop_alpha.data_center.render import render_status_markdown
from prop_alpha.data_center.status import assemble_data_center_status
from prop_alpha.options.gexbot.health import GexbotHealth

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def test_render_with_no_inputs_shows_not_available_everywhere():
    status = assemble_data_center_status(timestamp=_NOW)
    markdown = render_status_markdown(status)
    assert "UNKNOWN" in markdown
    assert markdown.count("not available") >= 3
    assert "- none" in markdown  # issues section


def test_render_includes_overall_status_and_timestamp():
    status = assemble_data_center_status(timestamp=_NOW)
    markdown = render_status_markdown(status)
    assert "2024-01-02T15:30:00" in markdown
    assert "**UNKNOWN**" in markdown


def test_render_futures_feed_section():
    feed = FeedHealth(
        provider="databento", instrument="ES", connection_state=ConnectionState.CONNECTED,
        messages_received=42, messages_per_second=7.5, sequence_gaps=0, last_message_age_seconds=1.2,
    )
    status = assemble_data_center_status(timestamp=_NOW, futures_feed=feed)
    markdown = render_status_markdown(status)
    assert "databento / ES" in markdown
    assert "CONNECTED" in markdown
    assert "42" in markdown


def test_render_options_feed_section_lists_available_metrics():
    options = GexbotHealth(
        connected=True, authenticated=True, last_update=_NOW, latency_ms=25.0,
        error_rate=0.02, data_age_seconds=3.0, available_metrics=("gex", "dex"),
    )
    status = assemble_data_center_status(timestamp=_NOW, options_feed=options)
    markdown = render_status_markdown(status)
    assert "gex, dex" in markdown
    assert "2.00%" in markdown


def test_render_quality_section_lists_failed_checks():
    report = DataQualityReport(
        checks=[CheckResult(name="invalid_prices", n_checked=100, n_violations=5)],
        score=90.0, severity="WARNING",
    )
    status = assemble_data_center_status(timestamp=_NOW, quality=report)
    markdown = render_status_markdown(status)
    assert "invalid_prices: 5/100" in markdown


def test_render_quality_section_no_failed_checks():
    status = assemble_data_center_status(timestamp=_NOW, quality=DataQualityReport())
    markdown = render_status_markdown(status)
    assert "Failed checks: none" in markdown


def test_render_issues_section_lists_each_issue():
    status = assemble_data_center_status(
        timestamp=_NOW,
        futures_feed=FeedHealth(
            provider="databento", instrument="ES", connection_state=ConnectionState.FAILED,
            messages_received=0, messages_per_second=0.0, sequence_gaps=0, last_message_age_seconds=None,
        ),
    )
    markdown = render_status_markdown(status)
    assert "## Issues" in markdown
    assert "connection_state=FAILED" in markdown


def test_render_market_state_completeness_formatted_as_percentage():
    status = assemble_data_center_status(timestamp=_NOW, market_state_completeness=0.6)
    markdown = render_status_markdown(status)
    assert "60%" in markdown
