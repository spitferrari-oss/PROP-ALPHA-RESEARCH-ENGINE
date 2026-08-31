import datetime as dt

from prop_alpha.options.gexbot.parser import parse_snapshot
from prop_alpha.options.normalize import normalize_gex_snapshot


def test_normalize_copies_underlying_and_all_metrics_unchanged():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "gex": 1.0e9, "spot": 4500.0}
    received_at = dt.datetime(2024, 1, 2, 10, 0, 5, tzinfo=dt.timezone.utc)
    gex_snapshot = parse_snapshot(raw, "SPX", received_at=received_at)

    snapshot = normalize_gex_snapshot(gex_snapshot)

    assert snapshot.underlying == "SPX"
    assert snapshot.gex.value == 1.0e9
    assert snapshot.spot.value == 4500.0
    assert snapshot.vanna.value is None  # missing stays missing, never defaulted


def test_normalize_defaults_timestamp_to_freshest_metric_timestamp():
    ts1 = dt.datetime(2024, 1, 2, 10, 0, 0, tzinfo=dt.timezone.utc)
    ts2 = dt.datetime(2024, 1, 2, 10, 5, 0, tzinfo=dt.timezone.utc)
    raw = {"gex": 1.0e9, "gex_timestamp": ts1, "spot": 4500.0, "spot_timestamp": ts2}
    gex_snapshot = parse_snapshot(raw, "SPX", received_at=ts2)

    snapshot = normalize_gex_snapshot(gex_snapshot)

    assert snapshot.timestamp == ts2  # the later of the two per-metric timestamps


def test_normalize_falls_back_to_now_when_nothing_available():
    gex_snapshot = parse_snapshot({}, "SPX")
    before = dt.datetime.now(dt.timezone.utc)
    snapshot = normalize_gex_snapshot(gex_snapshot)
    after = dt.datetime.now(dt.timezone.utc)
    assert before <= snapshot.timestamp <= after


def test_normalize_accepts_explicit_timestamp_override():
    gex_snapshot = parse_snapshot({"gex": 1.0}, "SPX")
    explicit = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    snapshot = normalize_gex_snapshot(gex_snapshot, timestamp=explicit)
    assert snapshot.timestamp == explicit


def test_normalize_passes_through_orderflow_state():
    gex_snapshot = parse_snapshot({}, "SPX")
    snapshot = normalize_gex_snapshot(gex_snapshot, orderflow_state={"net_premium": 1000.0})
    assert snapshot.orderflow_state == {"net_premium": 1000.0}
