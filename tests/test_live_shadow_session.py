import datetime as dt

import pytest

from prop_alpha.live_shadow.ledger import LiveShadowLedger
from prop_alpha.live_shadow.proposal import make_proposal
from prop_alpha.live_shadow.session import (
    LiveShadowMode,
    SessionState,
    get_live_shadow_status,
    run_live_shadow_session,
    stop_live_shadow_session,
)
from prop_alpha.providers.mocks import MockFuturesDataProvider
from prop_alpha.trading.no_trade import TradeState


def test_run_live_shadow_session_with_mock_provider_completes(tmp_path):
    provider = MockFuturesDataProvider(seed=1)
    status_path = tmp_path / "status.json"
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")

    status = run_live_shadow_session(
        provider, instrument="NQ", level=None, mode=LiveShadowMode.LIVE_SHADOW, data_source="MOCK",
        ledger=ledger, status_path=status_path,
    )
    assert status.state == SessionState.STOPPED.value
    assert status.n_events == 5  # MockFuturesDataProvider.subscribe_live delivers 5 bars
    assert status.data_source == "MOCK"


def test_default_pipeline_generates_no_proposals_no_edge_by_default(tmp_path):
    provider = MockFuturesDataProvider(seed=1)
    status_path = tmp_path / "status.json"
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")

    def always_propose(state):
        return make_proposal(
            timestamp=state.timestamp, instrument="NQ", direction="LONG",
            entry_price=state.price_state.get("close", 0.0), rationale="test",
        )

    status = run_live_shadow_session(
        provider, instrument="NQ", level=None, mode=LiveShadowMode.LIVE_SHADOW, data_source="MOCK",
        proposal_generator=always_propose, ledger=ledger, status_path=status_path,
    )
    # default no_trade_state_builder supplies no alpha_ev_per_day -> NO_EDGE blocks every bar
    assert status.n_proposals == 0
    assert ledger.read_proposals() == []


def test_custom_no_trade_state_builder_allows_proposals_through(tmp_path):
    provider = MockFuturesDataProvider(seed=1)
    status_path = tmp_path / "status.json"
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")

    def always_propose(state):
        return make_proposal(
            timestamp=state.timestamp, instrument="NQ", direction="LONG",
            entry_price=state.price_state.get("close", 0.0), rationale="test",
        )

    def eligible_no_trade_state(state):
        return TradeState(alpha_ev_per_day=50.0, data_quality_score=99.0)

    status = run_live_shadow_session(
        provider, instrument="NQ", level=None, mode=LiveShadowMode.LIVE_SHADOW, data_source="MOCK",
        proposal_generator=always_propose, no_trade_state_builder=eligible_no_trade_state,
        ledger=ledger, status_path=status_path,
    )
    assert status.n_proposals == 5
    assert len(ledger.read_proposals()) == 5


def test_invalid_data_source_raises(tmp_path):
    provider = MockFuturesDataProvider(seed=1)
    with pytest.raises(ValueError, match="data_source"):
        run_live_shadow_session(
            provider, instrument="NQ", level=None, mode=LiveShadowMode.LIVE_SHADOW,
            data_source="FAKE", status_path=tmp_path / "status.json",
        )


def test_provider_failure_reports_error_state(tmp_path):
    class _BrokenProvider:
        name = "broken"

        def subscribe_live(self, instrument, level, on_message):
            raise RuntimeError("connection refused")

    status = run_live_shadow_session(
        _BrokenProvider(), instrument="NQ", level=None, mode=LiveShadowMode.LIVE_SHADOW,
        data_source="REAL", status_path=tmp_path / "status.json",
    )
    assert status.state == SessionState.ERROR.value
    assert "connection refused" in status.message


def test_get_live_shadow_status_reads_persisted_status(tmp_path):
    status_path = tmp_path / "status.json"
    provider = MockFuturesDataProvider(seed=1)
    run_live_shadow_session(
        provider, instrument="NQ", level=None, mode=LiveShadowMode.LIVE_SHADOW,
        data_source="MOCK", status_path=status_path,
    )
    reloaded = get_live_shadow_status(status_path)
    assert reloaded.n_events == 5
    assert reloaded.state == SessionState.STOPPED.value


def test_get_live_shadow_status_with_no_session_reports_not_connected(tmp_path):
    status = get_live_shadow_status(tmp_path / "nonexistent.json")
    assert status.state == SessionState.NOT_CONNECTED.value
    assert status.data_source == "NOT_CONNECTED"


def test_stop_live_shadow_session_marks_stopped(tmp_path):
    status_path = tmp_path / "status.json"
    provider = MockFuturesDataProvider(seed=1)
    run_live_shadow_session(
        provider, instrument="NQ", level=None, mode=LiveShadowMode.LIVE_SHADOW,
        data_source="MOCK", status_path=status_path,
    )
    stopped = stop_live_shadow_session(status_path)
    assert stopped.state == SessionState.STOPPED.value
    assert "stopped by operator" in stopped.message
    assert get_live_shadow_status(status_path).message == "stopped by operator request"


def test_replay_shadow_mode_is_a_distinct_label_from_live_shadow(tmp_path):
    provider = MockFuturesDataProvider(seed=1)
    status = run_live_shadow_session(
        provider, instrument="NQ", level=None, mode=LiveShadowMode.REPLAY_SHADOW,
        data_source="REPLAY", status_path=tmp_path / "status.json",
    )
    assert status.mode == "REPLAY_SHADOW"
    assert status.mode != LiveShadowMode.LIVE_SHADOW.value


def test_live_auto_mode_is_representable_but_never_executes_anything(tmp_path):
    # The mode label itself is representable in status -- nothing about
    # requesting LIVE_AUTO here causes any order to be sent (this module
    # never imports execution.gateway at all).
    provider = MockFuturesDataProvider(seed=1)
    status = run_live_shadow_session(
        provider, instrument="NQ", level=None, mode=LiveShadowMode.LIVE_AUTO,
        data_source="MOCK", status_path=tmp_path / "status.json",
    )
    assert status.mode == "LIVE_AUTO"
    assert status.n_proposals == 0
