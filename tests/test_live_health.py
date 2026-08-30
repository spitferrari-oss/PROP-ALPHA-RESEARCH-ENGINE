import datetime as dt

from prop_alpha.data.live.buffer import BufferedMessage, MessageBuffer
from prop_alpha.data.live.connection_manager import ConnectionManager, ConnectionState
from prop_alpha.data.live.health import compute_feed_health


class _FakeConnectable:
    def connect(self):
        pass

    def disconnect(self):
        pass


def test_compute_feed_health_with_no_messages():
    connection = ConnectionManager(_FakeConnectable(), clock=lambda: 0.0)
    connection.connect()
    buffer = MessageBuffer()

    health = compute_feed_health("databento", "NQ", connection, buffer)

    assert health.connection_state == ConnectionState.CONNECTED
    assert health.messages_received == 0
    assert health.last_message_age_seconds is None


def test_compute_feed_health_reports_age_and_rate():
    connection = ConnectionManager(_FakeConnectable(), clock=lambda: 0.0)
    connection.connect()
    buffer = MessageBuffer()
    base = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    for i in range(3):
        buffer.append(BufferedMessage(received_at=base + dt.timedelta(seconds=i), sequence=i, payload={}))

    now = base + dt.timedelta(seconds=10)
    health = compute_feed_health("databento", "NQ", connection, buffer, now=now)

    assert health.messages_received == 3
    assert health.last_message_age_seconds == 8.0  # now - last message at t=2s
    assert health.sequence_gaps == 0


def test_compute_feed_health_reflects_stale_connection():
    clock_value = {"t": 0.0}
    connection = ConnectionManager(_FakeConnectable(), heartbeat_timeout_seconds=1.0, clock=lambda: clock_value["t"])
    connection.connect()
    clock_value["t"] = 100.0

    health = compute_feed_health("databento", "NQ", connection, MessageBuffer())
    assert health.connection_state == ConnectionState.STALE
