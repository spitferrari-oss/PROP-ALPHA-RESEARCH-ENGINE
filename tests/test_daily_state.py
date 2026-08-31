import pytest

from prop_alpha.prop.daily_state import (
    DailyState,
    DailyStateError,
    DailyStateMachine,
    evaluate_daily_state,
)


def test_new_machine_starts_pre_market():
    machine = DailyStateMachine()
    assert machine.state == DailyState.PRE_MARKET
    assert machine.is_terminal is False
    assert machine.can_trade is False


def test_legal_transition_updates_state_and_history():
    machine = DailyStateMachine()
    next_machine = machine.transition(DailyState.READY, "market opened")
    assert next_machine.state == DailyState.READY
    assert next_machine.history == (("PRE_MARKET", "READY", "market opened"),)
    assert machine.state == DailyState.PRE_MARKET  # original untouched (frozen)


def test_illegal_transition_raises():
    machine = DailyStateMachine()
    with pytest.raises(DailyStateError, match="Illegal transition"):
        machine.transition(DailyState.TRADE_ACTIVE)


def test_cannot_skip_pre_market_to_trade_active():
    machine = DailyStateMachine()
    with pytest.raises(DailyStateError):
        machine.transition(DailyState.TRADE_ACTIVE)


def test_terminal_state_daily_stop_rejects_any_transition():
    machine = DailyStateMachine(state=DailyState.DAILY_STOP)
    assert machine.is_terminal is True
    with pytest.raises(DailyStateError, match="terminal"):
        machine.transition(DailyState.READY)


def test_terminal_state_target_reached_rejects_any_transition():
    machine = DailyStateMachine(state=DailyState.TARGET_REACHED)
    with pytest.raises(DailyStateError, match="terminal"):
        machine.transition(DailyState.TRADE_ALLOWED)


def test_can_trade_true_only_in_trade_allowed_or_active():
    assert DailyStateMachine(state=DailyState.TRADE_ALLOWED).can_trade is True
    assert DailyStateMachine(state=DailyState.TRADE_ACTIVE).can_trade is True
    assert DailyStateMachine(state=DailyState.NO_TRADE).can_trade is False
    assert DailyStateMachine(state=DailyState.READY).can_trade is False


def test_evaluate_daily_state_pre_market_moves_to_ready():
    machine = evaluate_daily_state(DailyStateMachine(), eligible=True, position_open=False)
    assert machine.state == DailyState.READY


def test_evaluate_daily_state_eligible_moves_to_trade_allowed():
    machine = DailyStateMachine(state=DailyState.READY)
    result = evaluate_daily_state(machine, eligible=True, position_open=False)
    assert result.state == DailyState.TRADE_ALLOWED


def test_evaluate_daily_state_not_eligible_moves_to_no_trade():
    machine = DailyStateMachine(state=DailyState.READY)
    result = evaluate_daily_state(machine, eligible=False, position_open=False)
    assert result.state == DailyState.NO_TRADE


def test_evaluate_daily_state_position_open_moves_to_trade_active():
    machine = DailyStateMachine(state=DailyState.TRADE_ALLOWED)
    result = evaluate_daily_state(machine, eligible=True, position_open=True)
    assert result.state == DailyState.TRADE_ACTIVE


def test_evaluate_daily_state_target_reached_is_terminal():
    machine = DailyStateMachine(state=DailyState.TRADE_ALLOWED)
    result = evaluate_daily_state(
        machine, eligible=True, position_open=False, daily_pnl_r=3.5, target_r=3.0,
    )
    assert result.state == DailyState.TARGET_REACHED
    assert result.is_terminal is True


def test_evaluate_daily_state_daily_stop_is_terminal():
    machine = DailyStateMachine(state=DailyState.TRADE_ALLOWED)
    result = evaluate_daily_state(
        machine, eligible=True, position_open=False, daily_pnl_r=-3.5, stop_r=3.0,
    )
    assert result.state == DailyState.DAILY_STOP
    assert result.is_terminal is True


def test_evaluate_daily_state_once_terminal_stays_terminal_and_never_raises():
    machine = DailyStateMachine(state=DailyState.DAILY_STOP)
    result = evaluate_daily_state(machine, eligible=True, position_open=False, daily_pnl_r=1.0)
    assert result.state == DailyState.DAILY_STOP


def test_evaluate_daily_state_profit_protected():
    machine = DailyStateMachine(state=DailyState.TRADE_ALLOWED)
    result = evaluate_daily_state(
        machine, eligible=True, position_open=False, daily_pnl_r=2.0, profit_protect_r=1.5,
    )
    assert result.state == DailyState.PROFIT_PROTECTED


def test_evaluate_daily_state_loss_control():
    machine = DailyStateMachine(state=DailyState.TRADE_ALLOWED)
    result = evaluate_daily_state(
        machine, eligible=True, position_open=False, daily_pnl_r=-1.5, loss_control_r=1.0,
    )
    assert result.state == DailyState.LOSS_CONTROL


def test_evaluate_daily_state_routes_loss_control_to_profit_protected_via_trade_allowed():
    # LOSS_CONTROL has no direct edge to PROFIT_PROTECTED -- must route
    # through TRADE_ALLOWED without raising.
    machine = DailyStateMachine(state=DailyState.LOSS_CONTROL)
    result = evaluate_daily_state(
        machine, eligible=True, position_open=False, daily_pnl_r=2.0, profit_protect_r=1.5,
    )
    assert result.state == DailyState.PROFIT_PROTECTED
    # history shows the routing hop
    assert ("LOSS_CONTROL", "TRADE_ALLOWED", "routing through TRADE_ALLOWED") in result.history


def test_evaluate_daily_state_no_threshold_configured_does_not_evaluate_it():
    machine = DailyStateMachine(state=DailyState.TRADE_ALLOWED)
    result = evaluate_daily_state(machine, eligible=True, position_open=False, daily_pnl_r=-100.0)
    # no stop_r/loss_control_r configured -> not blocked despite huge loss
    assert result.state == DailyState.TRADE_ALLOWED


def test_evaluate_daily_state_thresholds_not_hardcoded():
    machine = DailyStateMachine(state=DailyState.TRADE_ALLOWED)
    a = evaluate_daily_state(machine, eligible=True, position_open=False, daily_pnl_r=1.0, target_r=0.5)
    b = evaluate_daily_state(machine, eligible=True, position_open=False, daily_pnl_r=1.0, target_r=5.0)
    assert a.state == DailyState.TARGET_REACHED
    assert b.state != DailyState.TARGET_REACHED
