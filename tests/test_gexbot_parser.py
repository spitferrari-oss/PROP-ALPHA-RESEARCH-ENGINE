import datetime as dt

from prop_alpha.options.gexbot.models import AvailabilityStatus
from prop_alpha.options.gexbot.parser import parse_snapshot


def _full_raw(ts=None):
    return {
        "timestamp": ts or "2024-01-02T10:00:00Z",
        "spot": 4500.0,
        "gex": 1.2e9,
        "dex": -3.4e8,
        "gamma_flip": 4480.0,
        "major_positive_gamma": 4550.0,
        "major_negative_gamma": 4400.0,
        "vanna": 5.0e7,
        "charm": -2.0e6,
        "vomma": 1.0e6,
        "skew": 0.12,
        "options_volume": 150000,
        "open_interest": 900000,
    }


def test_parse_snapshot_full_payload_all_available():
    snapshot = parse_snapshot(_full_raw(), "SPX", received_at=dt.datetime(2024, 1, 2, 10, 0, 5, tzinfo=dt.timezone.utc))
    assert snapshot.underlying == "SPX"
    for name in ("spot", "gex", "dex", "gamma_flip", "major_positive_gamma",
                 "major_negative_gamma", "vanna", "charm", "vomma", "skew",
                 "options_volume", "open_interest"):
        metric = getattr(snapshot, name)
        assert metric.value is not None
        assert metric.availability.status == AvailabilityStatus.AVAILABLE
        assert metric.availability.source == "gexbot"


def test_parse_snapshot_missing_field_is_unavailable_not_zero():
    raw = _full_raw()
    del raw["vanna"]
    del raw["charm"]
    snapshot = parse_snapshot(raw, "SPX")
    assert snapshot.vanna.value is None
    assert snapshot.vanna.availability.status == AvailabilityStatus.UNAVAILABLE
    assert snapshot.charm.value is None
    assert snapshot.charm.availability.status == AvailabilityStatus.UNAVAILABLE
    # a genuinely-reported zero must NOT be conflated with missing
    assert snapshot.spot.value == 4500.0


def test_parse_snapshot_recognizes_field_aliases():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "gamma_exposure": 5.0e8, "flip_point": 4490.0}
    snapshot = parse_snapshot(raw, "SPX", received_at=dt.datetime(2024, 1, 2, 10, 0, 5, tzinfo=dt.timezone.utc))
    assert snapshot.gex.value == 5.0e8
    assert snapshot.gex.availability.status == AvailabilityStatus.AVAILABLE
    assert snapshot.gamma_flip.value == 4490.0


def test_parse_snapshot_flags_stale_metric():
    old_ts = dt.datetime(2024, 1, 2, 9, 0, 0, tzinfo=dt.timezone.utc)
    raw = {"timestamp": old_ts.isoformat(), "gex": 1.0e9}
    received_at = old_ts + dt.timedelta(seconds=120)
    snapshot = parse_snapshot(raw, "SPX", received_at=received_at, stale_after_seconds=60.0)
    assert snapshot.gex.availability.status == AvailabilityStatus.STALE
    assert snapshot.gex.availability.freshness_seconds == 120.0


def test_parse_snapshot_zero_value_is_available_not_unavailable():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "skew": 0.0}
    snapshot = parse_snapshot(raw, "SPX", received_at=dt.datetime(2024, 1, 2, 10, 0, 5, tzinfo=dt.timezone.utc))
    assert snapshot.skew.value == 0.0
    assert snapshot.skew.availability.status == AvailabilityStatus.AVAILABLE


def test_parse_snapshot_empty_payload_all_unavailable():
    snapshot = parse_snapshot({}, "SPX")
    assert snapshot.gex.value is None
    assert snapshot.gex.availability.status == AvailabilityStatus.UNAVAILABLE
    assert snapshot.spot.availability.status == AvailabilityStatus.UNAVAILABLE


def test_parse_snapshot_accepts_epoch_timestamp():
    epoch = 1704189600  # 2024-01-02T10:00:00Z
    raw = {"timestamp": epoch, "gex": 1.0e9}
    snapshot = parse_snapshot(raw, "SPX", received_at=dt.datetime(2024, 1, 2, 10, 0, 0, tzinfo=dt.timezone.utc))
    assert snapshot.gex.availability.timestamp == dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
