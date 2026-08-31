import datetime as dt

from prop_alpha.options.gexbot.parser import parse_snapshot
from prop_alpha.options.levels import extract_levels
from prop_alpha.options.models import LevelType
from prop_alpha.options.normalize import normalize_gex_snapshot


def _snapshot(raw, received_at=None):
    received_at = received_at or dt.datetime(2024, 1, 2, 10, 0, 5, tzinfo=dt.timezone.utc)
    gex_snapshot = parse_snapshot(raw, "SPX", received_at=received_at)
    return normalize_gex_snapshot(gex_snapshot, timestamp=received_at)


def test_extract_levels_produces_gamma_flip_and_major_gamma():
    raw = {
        "timestamp": "2024-01-02T10:00:00Z", "spot": 4500.0,
        "gamma_flip": 4480.0, "major_positive_gamma": 4550.0, "major_negative_gamma": 4400.0,
    }
    snapshot = _snapshot(raw)
    levels = extract_levels(snapshot)

    by_metric = {level.metric: level for level in levels}
    assert by_metric["gamma_flip"].type == LevelType.GAMMA_FLIP
    assert by_metric["major_positive_gamma"].type == LevelType.MAJOR_GAMMA
    assert by_metric["major_negative_gamma"].type == LevelType.MAJOR_GAMMA
    assert len(levels) == 3


def test_extract_levels_computes_distance_from_spot_when_spot_available():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "spot": 4500.0, "gamma_flip": 4480.0}
    snapshot = _snapshot(raw)
    levels = extract_levels(snapshot)
    level = next(l for l in levels if l.metric == "gamma_flip")
    assert level.distance_from_spot == 4480.0 - 4500.0


def test_extract_levels_distance_is_none_without_spot():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "gamma_flip": 4480.0}
    snapshot = _snapshot(raw)
    levels = extract_levels(snapshot)
    level = next(l for l in levels if l.metric == "gamma_flip")
    assert level.distance_from_spot is None


def test_extract_levels_skips_unavailable_metrics():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "spot": 4500.0, "gamma_flip": 4480.0}
    snapshot = _snapshot(raw)  # major_positive/negative_gamma missing entirely
    levels = extract_levels(snapshot)
    assert len(levels) == 1
    assert levels[0].metric == "gamma_flip"


def test_extract_levels_empty_snapshot_yields_no_levels():
    snapshot = _snapshot({})
    assert extract_levels(snapshot) == []


def test_extract_levels_strength_is_always_none_at_this_phase():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "gamma_flip": 4480.0}
    snapshot = _snapshot(raw)
    levels = extract_levels(snapshot)
    assert all(level.strength is None for level in levels)


def test_extract_levels_custom_source_label():
    raw = {"timestamp": "2024-01-02T10:00:00Z", "gamma_flip": 4480.0}
    snapshot = _snapshot(raw)
    levels = extract_levels(snapshot, source="gexbot-pro")
    assert all(level.source == "gexbot-pro" for level in levels)
