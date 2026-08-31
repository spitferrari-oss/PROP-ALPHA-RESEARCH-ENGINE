import datetime as dt

from prop_alpha.options.gexbot.health import compute_health
from prop_alpha.options.gexbot.parser import parse_snapshot


def test_compute_health_no_snapshot_yet():
    health = compute_health(snapshot=None, connected=True, authenticated=True, n_polls=0, n_errors=0)
    assert health.connected is True
    assert health.last_update is None
    assert health.available_metrics == ()
    assert health.error_rate == 0.0


def test_compute_health_with_full_snapshot():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "gex": 1.0e9, "dex": 2.0e8, "spot": 4500.0}
    snapshot = parse_snapshot(raw, "SPX", received_at=dt.datetime(2024, 1, 2, 10, 0, 1, tzinfo=dt.timezone.utc))
    health = compute_health(snapshot, connected=True, authenticated=True, n_polls=10, n_errors=1)
    assert set(health.available_metrics) == {"gex", "dex", "spot"}
    assert health.error_rate == 0.1
    assert health.data_age_seconds is not None
    assert health.last_update is not None


def test_compute_health_partial_snapshot_excludes_unavailable_metrics():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "gex": 1.0e9}
    snapshot = parse_snapshot(raw, "SPX")
    health = compute_health(snapshot, connected=True, authenticated=True, n_polls=1, n_errors=0)
    assert health.available_metrics == ("gex",)


def test_compute_health_zero_polls_has_zero_error_rate():
    health = compute_health(snapshot=None, connected=False, authenticated=False, n_polls=0, n_errors=0)
    assert health.error_rate == 0.0
    assert health.connected is False
