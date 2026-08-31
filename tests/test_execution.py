import pytest

from prop_alpha.execution.base import ExecutionGateway, OrderRequest
from prop_alpha.execution.gateway import LIVE_EXECUTION_ENABLED, LiveExecutionDisabledError, get_gateway
from prop_alpha.execution.paper import PaperExecutionGateway


def test_live_execution_enabled_is_false():
    assert LIVE_EXECUTION_ENABLED is False


def test_paper_gateway_satisfies_the_abc():
    gateway = PaperExecutionGateway()
    assert isinstance(gateway, ExecutionGateway)
    assert gateway.live_execution_enabled is False


def test_get_gateway_default_returns_paper():
    gateway = get_gateway()
    assert isinstance(gateway, PaperExecutionGateway)


def test_get_gateway_explicit_paper_returns_paper():
    gateway = get_gateway("paper")
    assert isinstance(gateway, PaperExecutionGateway)


def test_get_gateway_live_raises():
    with pytest.raises(LiveExecutionDisabledError, match="LIVE EXECUTION: DISABLED"):
        get_gateway("live")


def test_get_gateway_any_non_paper_name_raises():
    with pytest.raises(LiveExecutionDisabledError):
        get_gateway("interactive_brokers")
    with pytest.raises(LiveExecutionDisabledError):
        get_gateway("tradovate")


def test_paper_submit_order_simulated_fill():
    gateway = PaperExecutionGateway()
    result = gateway.submit_order(OrderRequest(instrument="NQ", direction="LONG", quantity=1, limit_price=20000.0))
    assert result.status == "SIMULATED_FILLED"
    assert result.filled_price == 20000.0
    assert "no real order" in result.message.lower()


def test_paper_submit_order_updates_positions():
    gateway = PaperExecutionGateway()
    gateway.submit_order(OrderRequest(instrument="NQ", direction="LONG", quantity=2, limit_price=20000.0))
    positions = gateway.get_positions()
    assert len(positions) == 1
    assert positions[0].instrument == "NQ"
    assert positions[0].quantity == 2


def test_paper_opposite_order_flattens_position():
    gateway = PaperExecutionGateway()
    gateway.submit_order(OrderRequest(instrument="NQ", direction="LONG", quantity=1, limit_price=20000.0))
    gateway.submit_order(OrderRequest(instrument="NQ", direction="SHORT", quantity=1, limit_price=20010.0))
    assert gateway.get_positions() == []


def test_paper_close_position_with_no_position_rejected():
    gateway = PaperExecutionGateway()
    result = gateway.close_position("NQ")
    assert result.status == "REJECTED"


def test_paper_close_position_after_open_succeeds():
    gateway = PaperExecutionGateway()
    gateway.submit_order(OrderRequest(instrument="NQ", direction="LONG", quantity=1, limit_price=20000.0))
    result = gateway.close_position("NQ")
    assert result.status == "SIMULATED_FILLED"
    assert gateway.get_positions() == []


def test_paper_modify_and_cancel_always_rejected():
    gateway = PaperExecutionGateway()
    assert gateway.modify_order("ANY").status == "REJECTED"
    assert gateway.cancel_order("ANY").status == "REJECTED"


def test_paper_account_state_reflects_starting_equity_with_no_positions():
    gateway = PaperExecutionGateway(starting_equity=50_000.0)
    state = gateway.get_account_state()
    assert state.equity == 50_000.0
    assert state.open_positions == 0
