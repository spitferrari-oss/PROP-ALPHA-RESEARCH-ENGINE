from prop_alpha.agents.risk_agent import evaluate_risk_gates
from prop_alpha.config import PropFirmConfig


def _prop(**overrides):
    base = dict(account_size=100_000.0, profit_target=8_000.0, max_daily_loss=5_000.0,
                max_total_loss=10_000.0, trailing_drawdown=True, minimum_trading_days=5,
                payout_threshold=8_000.0)
    base.update(overrides)
    return PropFirmConfig(**base)


def _gate_by_name(gates, name):
    return next(g for g in gates if g.name == name)


def test_sizing_feasible_when_some_policy_sizes_trades():
    policies = [
        {"policy_name": "A", "n_trades": 0, "avg_contracts": 0.0},
        {"policy_name": "B", "n_trades": 42, "avg_contracts": 2.0},
    ]
    gates = evaluate_risk_gates({"max_drawdown": -5000.0}, policies, _prop())
    assert _gate_by_name(gates, "SIZING_FEASIBLE").status == "PASS"


def test_sizing_infeasible_when_no_policy_sizes_any_trade():
    policies = [{"policy_name": "A", "n_trades": 0, "avg_contracts": 0.0}]
    gates = evaluate_risk_gates({"max_drawdown": -5000.0}, policies, _prop())
    assert _gate_by_name(gates, "SIZING_FEASIBLE").status == "FAIL"


def test_sizing_not_evaluated_when_no_policies():
    gates = evaluate_risk_gates({"max_drawdown": -5000.0}, None, _prop())
    assert _gate_by_name(gates, "SIZING_FEASIBLE").status == "NOT_EVALUATED"


def test_drawdown_within_limits_pass():
    gates = evaluate_risk_gates({"max_drawdown": -5000.0}, [], _prop(max_total_loss=10_000.0))
    assert _gate_by_name(gates, "DRAWDOWN_WITHIN_LIMITS").status == "PASS"


def test_drawdown_exceeds_limits_fail():
    gates = evaluate_risk_gates({"max_drawdown": -15000.0}, [], _prop(max_total_loss=10_000.0))
    assert _gate_by_name(gates, "DRAWDOWN_WITHIN_LIMITS").status == "FAIL"


def test_drawdown_not_evaluated_when_missing():
    gates = evaluate_risk_gates({}, [], _prop())
    assert _gate_by_name(gates, "DRAWDOWN_WITHIN_LIMITS").status == "NOT_EVALUATED"


def test_drawdown_nan_not_evaluated():
    gates = evaluate_risk_gates({"max_drawdown": float("nan")}, [], _prop())
    assert _gate_by_name(gates, "DRAWDOWN_WITHIN_LIMITS").status == "NOT_EVALUATED"
