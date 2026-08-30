import numpy as np
import pandas as pd

from prop_alpha.agents.critic import evaluate_critic_findings
from prop_alpha.config import AgentsConfig


def _days(n):
    return list(pd.bdate_range("2024-01-01", periods=n).date)


def _clean_alpha_result(**overrides):
    base = dict(n_trades=200, dsr=0.9, breakeven_cost_profile="stress")
    base.update(overrides)
    return base


def test_no_findings_for_clean_alpha():
    days = _days(60)
    alpha_pnl = pd.Series(np.random.default_rng(0).normal(100, 50, 60), index=days)
    ce_table = pd.DataFrame({"regime_rule": ["TREND_UP", "RANGE"], "ev_dollars": [50.0, 30.0]})
    findings = evaluate_critic_findings(
        _clean_alpha_result(), {"pbo": 0.1}, ce_table, alpha_pnl, {}, days,
    )
    assert findings == []


def test_low_sample_flagged():
    findings = evaluate_critic_findings(
        _clean_alpha_result(n_trades=10), {"pbo": 0.1}, None, None, None, [],
        config=AgentsConfig(min_trades_for_sample_gate=100),
    )
    assert any(f.category == "LOW_SAMPLE" for f in findings)


def test_overfit_risk_from_low_dsr():
    findings = evaluate_critic_findings(
        _clean_alpha_result(dsr=0.1), {"pbo": 0.1}, None, None, None, [],
    )
    high = [f for f in findings if f.category == "OVERFIT_RISK" and f.severity == "HIGH"]
    assert len(high) == 1


def test_overfit_risk_from_high_pbo():
    findings = evaluate_critic_findings(
        _clean_alpha_result(), {"pbo": 0.8}, None, None, None, [],
    )
    medium = [f for f in findings if f.category == "OVERFIT_RISK" and f.severity == "MEDIUM"]
    assert len(medium) == 1


def test_regime_fragile_flagged_when_majority_negative():
    ce_table = pd.DataFrame({
        "regime_rule": ["TREND_UP", "RANGE", "COMPRESSION"],
        "ev_dollars": [50.0, -10.0, -20.0],
    })
    findings = evaluate_critic_findings(
        _clean_alpha_result(), {"pbo": 0.1}, ce_table, None, None, [],
    )
    assert any(f.category == "REGIME_FRAGILE" for f in findings)


def test_execution_sensitive_none_is_high_severity():
    findings = evaluate_critic_findings(
        _clean_alpha_result(breakeven_cost_profile=None), {"pbo": 0.1}, None, None, None, [],
    )
    match = [f for f in findings if f.category == "EXECUTION_SENSITIVE"]
    assert len(match) == 1 and match[0].severity == "HIGH"


def test_execution_sensitive_optimistic_is_medium_severity():
    findings = evaluate_critic_findings(
        _clean_alpha_result(breakeven_cost_profile="optimistic"), {"pbo": 0.1}, None, None, None, [],
    )
    match = [f for f in findings if f.category == "EXECUTION_SENSITIVE"]
    assert len(match) == 1 and match[0].severity == "MEDIUM"


def test_hidden_correlation_flagged_for_near_identical_pnl():
    days = _days(80)
    base_pnl = pd.Series(np.random.default_rng(1).normal(0, 100, 80), index=days)
    alpha_pnl = base_pnl + 1.0  # nearly identical, tiny offset
    findings = evaluate_critic_findings(
        _clean_alpha_result(), {"pbo": 0.1}, None, alpha_pnl, {"Simple Breakout": base_pnl}, days,
    )
    assert any(f.category == "HIDDEN_CORRELATION" for f in findings)


def test_no_hidden_correlation_for_independent_pnl():
    days = _days(80)
    rng = np.random.default_rng(2)
    alpha_pnl = pd.Series(rng.normal(0, 100, 80), index=days)
    base_pnl = pd.Series(rng.normal(0, 100, 80), index=days)
    findings = evaluate_critic_findings(
        _clean_alpha_result(), {"pbo": 0.1}, None, alpha_pnl, {"Simple Breakout": base_pnl}, days,
    )
    assert not any(f.category == "HIDDEN_CORRELATION" for f in findings)
