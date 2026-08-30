import datetime as dt

from prop_alpha.data.live.buffer import BufferedMessage, MessageBuffer


def _msg(seconds_offset: float, sequence, base=None):
    base = base or dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    return BufferedMessage(
        received_at=base + dt.timedelta(seconds=seconds_offset),
        sequence=sequence,
        payload={},
    )


def test_empty_buffer_reports_zero_rate_and_no_gaps():
    buffer = MessageBuffer()
    assert len(buffer) == 0
    assert buffer.last() is None
    assert buffer.messages_per_second() == 0.0
    assert buffer.sequence_gaps() == 0


def test_messages_per_second_counts_within_trailing_window():
    buffer = MessageBuffer()
    for i in range(5):
        buffer.append(_msg(seconds_offset=i * 0.1, sequence=i))
    # last message at t=0.4s; a 1s window should include all 5
    assert buffer.messages_per_second(window_seconds=1.0) == 5.0
    # a 0.05s window should include only the last message -> 1 / 0.05 = 20/s
    assert buffer.messages_per_second(window_seconds=0.05) == 20.0


def test_sequence_gaps_detects_missing_numbers():
    buffer = MessageBuffer()
    for seq in [1, 2, 3, 5, 6, 9]:
        buffer.append(_msg(seconds_offset=seq, sequence=seq))
    # gaps: 3->5 (missing 4), 6->9 (missing 7,8) => 2 gap events
    assert buffer.sequence_gaps() == 2


def test_sequence_gaps_ignores_messages_without_sequence():
    buffer = MessageBuffer()
    buffer.append(_msg(seconds_offset=1, sequence=1))
    buffer.append(_msg(seconds_offset=2, sequence=None))
    buffer.append(_msg(seconds_offset=3, sequence=2))
    assert buffer.sequence_gaps() == 0


def test_buffer_respects_maxlen():
    buffer = MessageBuffer(maxlen=3)
    for i in range(5):
        buffer.append(_msg(seconds_offset=i, sequence=i))
    assert len(buffer) == 3
    assert buffer.last().sequence == 4
