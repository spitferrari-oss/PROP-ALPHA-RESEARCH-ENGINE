import pytest

from prop_alpha.data.live.connection_manager import (
    BackoffPolicy,
    ConnectionManager,
    ConnectionState,
)


class _FakeConnectable:
    def __init__(self, fail_connect: bool = False):
        self.connect_calls = 0
        self.disconnect_calls = 0
        self._fail_connect = fail_connect

    def connect(self):
        self.connect_calls += 1
        if self._fail_connect:
            raise ConnectionError("boom")

    def disconnect(self):
        self.disconnect_calls += 1


class _FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_backoff_policy_doubles_up_to_max():
    policy = BackoffPolicy(initial_seconds=1.0, max_seconds=10.0, multiplier=2.0)
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 4.0
    assert policy.delay_for_attempt(10) == 10.0  # capped


def test_connect_transitions_to_connected():
    connectable = _FakeConnectable()
    manager = ConnectionManager(connectable, clock=_FakeClock())
    manager.connect()
    assert manager.state == ConnectionState.CONNECTED
    assert connectable.connect_calls == 1


def test_failed_connect_sets_failed_state_and_reraises():
    connectable = _FakeConnectable(fail_connect=True)
    manager = ConnectionManager(connectable, clock=_FakeClock())
    with pytest.raises(ConnectionError):
        manager.connect()
    assert manager.state == ConnectionState.FAILED


def test_disconnect_resets_state():
    connectable = _FakeConnectable()
    manager = ConnectionManager(connectable, clock=_FakeClock())
    manager.connect()
    manager.disconnect()
    assert manager.state == ConnectionState.DISCONNECTED
    assert connectable.disconnect_calls == 1


def test_stale_detection_uses_heartbeat_timeout():
    clock = _FakeClock()
    connectable = _FakeConnectable()
    manager = ConnectionManager(connectable, heartbeat_timeout_seconds=5.0, clock=clock)
    manager.connect()
    assert manager.check_health() == ConnectionState.CONNECTED

    clock.now += 10.0
    assert manager.check_health() == ConnectionState.STALE


def test_heartbeat_clears_stale_state():
    clock = _FakeClock()
    connectable = _FakeConnectable()
    manager = ConnectionManager(connectable, heartbeat_timeout_seconds=5.0, clock=clock)
    manager.connect()
    clock.now += 10.0
    manager.check_health()
    assert manager.state == ConnectionState.STALE

    manager.on_heartbeat()
    assert manager.state == ConnectionState.CONNECTED


def test_reconnect_uses_injected_sleep_and_backoff_without_real_delay():
    clock = _FakeClock()
    connectable = _FakeConnectable()
    sleeps = []
    manager = ConnectionManager(
        connectable, backoff=BackoffPolicy(initial_seconds=2.0), clock=clock,
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )
    manager.connect()
    manager.reconnect()
    assert sleeps == [2.0]
    assert manager.state == ConnectionState.CONNECTED
    assert connectable.connect_calls == 2


def test_reconnect_ignores_disconnect_errors_on_a_never_connected_client():
    class _AlwaysFailsDisconnect(_FakeConnectable):
        def disconnect(self):
            raise RuntimeError("not connected")

    manager = ConnectionManager(_AlwaysFailsDisconnect(), clock=_FakeClock(), sleep_fn=lambda s: None)
    manager.reconnect()  # must not raise
    assert manager.state == ConnectionState.CONNECTED
