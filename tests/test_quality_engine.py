import pandas as pd

from prop_alpha.data.live.connection_manager import ConnectionState
from prop_alpha.data.live.health import FeedHealth
from prop_alpha.data.quality_config import BlockedOnFlags, DataQualityConfig
from prop_alpha.data.quality_engine import (
    DEFAULT_CHECK_WEIGHTS,
    evaluate_batch_quality,
    evaluate_live_quality,
    is_blocked,
    severity_for_score,
)


def _clean_bars(n=20):
    ts = pd.date_range("2024-01-02 09:30", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "open": [100.0 + i * 0.1 for i in range(n)],
        "high": [100.2 + i * 0.1 for i in range(n)],
        "low": [99.9 + i * 0.1 for i in range(n)],
        "close": [100.1 + i * 0.1 for i in range(n)],
        "volume": [10 + i for i in range(n)],
    })


def _quotes(n=10):
    ts = pd.date_range("2024-01-02 09:30", periods=n, freq="1s", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "bid_price": [100.0] * n, "ask_price": [100.25] * n})


def _feed_health(age_seconds, provider="databento", instrument="NQ"):
    return FeedHealth(
        provider=provider, instrument=instrument, connection_state=ConnectionState.CONNECTED,
        messages_received=10, messages_per_second=2.0, sequence_gaps=0,
        last_message_age_seconds=age_seconds,
    )


def test_severity_bands():
    assert severity_for_score(100.0) == "EXCELLENT"
    assert severity_for_score(99.0) == "EXCELLENT"
    assert severity_for_score(98.99) == "GOOD"
    assert severity_for_score(97.0) == "GOOD"
    assert severity_for_score(96.99) == "WARNING"
    assert severity_for_score(95.0) == "WARNING"
    assert severity_for_score(94.99) == "CRITICAL"
    assert severity_for_score(0.0) == "CRITICAL"


def test_clean_bars_score_100_and_excellent():
    report = evaluate_batch_quality(_clean_bars(), expected_freq=pd.Timedelta(minutes=1))
    assert report.score == 100.0
    assert report.severity == "EXCELLENT"
    assert report.failed_checks() == []


def test_duplicate_timestamps_penalized():
    df = _clean_bars()
    df.loc[5, "timestamp"] = df.loc[4, "timestamp"]
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "duplicate_timestamps")
    assert check.n_violations == 1
    assert report.score < 100.0


def test_out_of_order_timestamps_detected():
    df = _clean_bars()
    df.loc[3, "timestamp"], df.loc[4, "timestamp"] = df.loc[4, "timestamp"], df.loc[3, "timestamp"]
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "out_of_order")
    assert check.n_violations >= 1


def test_invalid_prices_detected():
    df = _clean_bars()
    df.loc[2, "close"] = -5.0
    df.loc[7, "open"] = float("nan")
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "invalid_prices")
    assert check.n_violations == 2


def test_negative_volume_detected():
    df = _clean_bars()
    df.loc[1, "volume"] = -10
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "negative_volume")
    assert check.n_violations == 1


def test_missing_timestamps_detected_with_expected_freq():
    df = _clean_bars(n=10).drop(index=5).reset_index(drop=True)
    report = evaluate_batch_quality(df, expected_freq=pd.Timedelta(minutes=1))
    check = next(c for c in report.checks if c.name == "missing_timestamps")
    assert check.n_violations == 1


def test_missing_timestamps_not_applicable_without_expected_freq():
    df = _clean_bars(n=10).drop(index=5).reset_index(drop=True)
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "missing_timestamps")
    assert check.applicable is False
    assert check.violation_rate == 0.0


def test_abnormal_timestamp_jump_detected():
    df = _clean_bars(n=5)
    df.loc[4, "timestamp"] = df.loc[3, "timestamp"] + pd.Timedelta(minutes=30)
    report = evaluate_batch_quality(df, expected_freq=pd.Timedelta(minutes=1))
    check = next(c for c in report.checks if c.name == "abnormal_timestamp_jumps")
    assert check.n_violations == 1


def test_contract_mismatch_detected():
    df = _clean_bars(n=5)
    df["symbol"] = ["NQZ4"] * 4 + ["ESZ4"]
    report = evaluate_batch_quality(df, expected_instrument="NQ")
    check = next(c for c in report.checks if c.name == "contract_mismatch")
    assert check.n_violations == 1


def test_contract_mismatch_not_applicable_without_expected_instrument():
    df = _clean_bars(n=5)
    df["symbol"] = "NQZ4"
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "contract_mismatch")
    assert check.applicable is False


def test_crossed_book_detected():
    df = _quotes()
    df.loc[3, "bid_price"] = 100.5  # bid above ask
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "crossed_book")
    assert check.n_violations == 1


def test_locked_book_detected():
    df = _quotes()
    df.loc[3, "bid_price"] = df.loc[3, "ask_price"]
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "locked_book")
    assert check.n_violations == 1


def test_impossible_spread_detected_with_max_spread_ticks():
    df = _quotes()
    df.loc[3, "ask_price"] = 200.0  # absurd spread
    report = evaluate_batch_quality(df, max_spread_ticks=10, tick_size=0.25)
    check = next(c for c in report.checks if c.name == "impossible_spreads")
    assert check.n_violations == 1


def test_book_checks_not_applicable_for_bars_without_bid_ask():
    report = evaluate_batch_quality(_clean_bars())
    for name in ("crossed_book", "locked_book", "impossible_spreads"):
        check = next(c for c in report.checks if c.name == name)
        assert check.applicable is False


def test_sequence_gap_detected():
    df = _quotes(n=5)
    df["sequence"] = [1, 2, 3, 5, 6]  # gap: missing 4
    report = evaluate_batch_quality(df)
    check = next(c for c in report.checks if c.name == "sequence_gaps")
    assert check.n_violations == 1


def test_sequence_gaps_not_applicable_without_sequence_column():
    report = evaluate_batch_quality(_clean_bars())
    check = next(c for c in report.checks if c.name == "sequence_gaps")
    assert check.applicable is False


def test_evaluate_live_quality_flags_stale_feed():
    batch_report = evaluate_batch_quality(_clean_bars())
    report = evaluate_live_quality(
        batch_report, feed_health=_feed_health(age_seconds=30.0),
        stale_threshold_seconds=3.0, n_messages=20,
    )
    check = next(c for c in report.checks if c.name == "stale_feed")
    assert check.n_violations == 1
    assert report.score < batch_report.score


def test_evaluate_live_quality_fresh_feed_no_penalty():
    batch_report = evaluate_batch_quality(_clean_bars())
    report = evaluate_live_quality(
        batch_report, feed_health=_feed_health(age_seconds=0.5),
        stale_threshold_seconds=3.0, n_messages=20,
    )
    check = next(c for c in report.checks if c.name == "stale_feed")
    assert check.n_violations == 0


def test_evaluate_live_quality_counts_malformed_payloads():
    batch_report = evaluate_batch_quality(_clean_bars())
    report = evaluate_live_quality(
        batch_report, feed_health=_feed_health(age_seconds=0.1),
        stale_threshold_seconds=3.0, n_messages=100, n_malformed=5,
    )
    check = next(c for c in report.checks if c.name == "malformed_payload")
    assert check.n_violations == 5
    assert check.n_checked == 100


def test_is_blocked_true_for_sequence_gap_regardless_of_score():
    df = _quotes(n=100)
    df["sequence"] = list(range(1, 100)) + [101]  # one gap near the end, tiny score impact
    report = evaluate_batch_quality(df)
    blocked, reasons = is_blocked(report, DataQualityConfig())
    assert blocked
    assert any("sequence_gap" in r for r in reasons)


def test_is_blocked_false_when_no_flagged_violations():
    report = evaluate_batch_quality(_clean_bars())
    blocked, reasons = is_blocked(report, DataQualityConfig())
    assert not blocked
    assert reasons == []


def test_is_blocked_respects_disabled_flags():
    df = _quotes(n=5)
    df["sequence"] = [1, 2, 3, 5, 6]
    report = evaluate_batch_quality(df)
    config = DataQualityConfig(
        blocked_on=BlockedOnFlags(sequence_gap=False, timestamp_error=False, malformed_payload=False)
    )
    blocked, reasons = is_blocked(report, config)
    assert not blocked
    assert reasons == []


def test_default_check_weights_cover_every_check_name():
    report = evaluate_batch_quality(_clean_bars())
    for check in report.checks:
        assert check.name in DEFAULT_CHECK_WEIGHTS
