import datetime as dt

from prop_alpha.data.live.recorder import build_envelope
from prop_alpha.replay.engine import replay_envelopes

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _envelope(offset_seconds: float, payload: dict) -> "object":
    return build_envelope(
        provider="databento", instrument="ES", schema="ohlcv-1s", payload=payload,
        timestamp_exchange=_NOW + dt.timedelta(seconds=offset_seconds),
    )


def test_replay_dispatches_in_timestamp_order_regardless_of_input_order():
    envelopes = [_envelope(2, {"i": 2}), _envelope(0, {"i": 0}), _envelope(1, {"i": 1})]
    dispatched = []
    replay_envelopes(envelopes, on_envelope=lambda e: dispatched.append(e.payload["i"]))
    assert dispatched == [0, 1, 2]


def test_replay_ties_broken_by_original_position():
    envelopes = [_envelope(0, {"i": "a"}), _envelope(0, {"i": "b"}), _envelope(0, {"i": "c"})]
    dispatched = []
    replay_envelopes(envelopes, on_envelope=lambda e: dispatched.append(e.payload["i"]))
    assert dispatched == ["a", "b", "c"]


def test_replay_is_deterministic_across_different_input_orderings():
    a = [_envelope(2, {"i": 2}), _envelope(0, {"i": 0}), _envelope(1, {"i": 1})]
    b = [_envelope(1, {"i": 1}), _envelope(2, {"i": 2}), _envelope(0, {"i": 0})]

    dispatched_a, dispatched_b = [], []
    replay_envelopes(a, on_envelope=lambda e: dispatched_a.append(e.payload["i"]))
    replay_envelopes(b, on_envelope=lambda e: dispatched_b.append(e.payload["i"]))
    assert dispatched_a == dispatched_b == [0, 1, 2]


def test_replay_speed_none_never_sleeps():
    envelopes = [_envelope(0, {}), _envelope(5, {})]
    sleep_calls = []
    replay_envelopes(envelopes, on_envelope=lambda e: None, speed=None, sleep_fn=sleep_calls.append)
    assert sleep_calls == []


def test_replay_speed_zero_never_sleeps():
    envelopes = [_envelope(0, {}), _envelope(5, {})]
    sleep_calls = []
    replay_envelopes(envelopes, on_envelope=lambda e: None, speed=0, sleep_fn=sleep_calls.append)
    assert sleep_calls == []


def test_replay_speed_one_sleeps_for_the_real_gap():
    envelopes = [_envelope(0, {}), _envelope(5, {})]
    sleep_calls = []
    replay_envelopes(envelopes, on_envelope=lambda e: None, speed=1.0, sleep_fn=sleep_calls.append)
    assert sleep_calls == [5.0]


def test_replay_speed_two_halves_the_sleep_duration():
    envelopes = [_envelope(0, {}), _envelope(10, {})]
    sleep_calls = []
    replay_envelopes(envelopes, on_envelope=lambda e: None, speed=2.0, sleep_fn=sleep_calls.append)
    assert sleep_calls == [5.0]


def test_replay_first_envelope_never_triggers_a_sleep():
    envelopes = [_envelope(0, {})]
    sleep_calls = []
    replay_envelopes(envelopes, on_envelope=lambda e: None, speed=1.0, sleep_fn=sleep_calls.append)
    assert sleep_calls == []


def test_replay_negative_gap_from_tied_timestamps_is_clamped_not_negative():
    envelopes = [_envelope(0, {"i": "a"}), _envelope(0, {"i": "b"})]
    sleep_calls = []
    replay_envelopes(envelopes, on_envelope=lambda e: None, speed=1.0, sleep_fn=sleep_calls.append)
    assert sleep_calls == []


def test_replay_result_reports_event_count_and_bounds():
    envelopes = [_envelope(0, {}), _envelope(5, {})]
    result = replay_envelopes(envelopes, on_envelope=lambda e: None)
    assert result.n_events == 2
    assert result.start_timestamp == _NOW
    assert result.end_timestamp == _NOW + dt.timedelta(seconds=5)


def test_replay_result_empty_input():
    result = replay_envelopes([], on_envelope=lambda e: None)
    assert result.n_events == 0
    assert result.start_timestamp is None
    assert result.end_timestamp is None
