import pytest

from prop_alpha.trading.no_trade import (
    NoTradeReason,
    NoTradeThresholds,
    TradeState,
    evaluate_trade_eligibility,
    should_trade,
)

_GOOD_STATE = TradeState(
    alpha_ev_per_day=50.0,
    data_quality_score=99.0,
    regime="TREND_UP",
    valid_regimes=("TREND_UP", "BREAKOUT"),
    relative_volume=1.2,
    required_data_age_seconds={"futures": 1.0, "options": 5.0},
    trades_today=0,
    max_trades_day=3,
    daily_pnl_r=0.0,
    distance_to_prop_breach_r=5.0,
    model_uncertainty=0.1,
    required_options_metrics=("gex", "dex"),
    available_options_metrics=("gex", "dex", "vanna"),
    execution_quality_score=0.9,
    high_impact_event_within_minutes=120.0,
    event_blackout_minutes=15.0,
)


def test_fully_specified_good_state_is_eligible():
    result = evaluate_trade_eligibility(_GOOD_STATE)
    assert result.eligible is True
    assert result.blocked_reasons == ()


def test_should_trade_matches_eligible():
    assert should_trade(_GOOD_STATE) is True


def test_default_state_with_no_data_is_not_eligible():
    result = evaluate_trade_eligibility(TradeState())
    assert result.eligible is False
    assert NoTradeReason.NO_EDGE in result.blocked_reasons
    assert NoTradeReason.LOW_DATA_QUALITY in result.blocked_reasons


def test_missing_alpha_ev_blocks_no_edge():
    from dataclasses import replace
    state = replace(_GOOD_STATE, alpha_ev_per_day=None)
    result = evaluate_trade_eligibility(state)
    assert result.eligible is False
    assert NoTradeReason.NO_EDGE in result.blocked_reasons
    assert result.alpha_ev_valid is False


def test_negative_alpha_ev_blocks_no_edge():
    from dataclasses import replace
    state = replace(_GOOD_STATE, alpha_ev_per_day=-10.0)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.NO_EDGE in result.blocked_reasons


def test_bad_regime_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, regime="PANIC")
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.BAD_REGIME in result.blocked_reasons
    assert result.regime_valid is False


def test_regime_not_evaluated_is_a_warning_not_a_block():
    from dataclasses import replace
    state = replace(_GOOD_STATE, regime=None, valid_regimes=None)
    result = evaluate_trade_eligibility(state)
    assert result.regime_valid is None
    assert NoTradeReason.BAD_REGIME not in result.blocked_reasons
    assert any("regime" in w for w in result.warnings)
    assert result.eligible is True  # still eligible on everything else


def test_low_liquidity_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, relative_volume=0.05)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.LOW_LIQUIDITY in result.blocked_reasons


def test_high_event_risk_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, high_impact_event_within_minutes=5.0, event_blackout_minutes=15.0)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.HIGH_EVENT_RISK in result.blocked_reasons
    assert result.event_risk is True


def test_stale_required_data_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, required_data_age_seconds={"futures": 1000.0})
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.STALE_REQUIRED_DATA in result.blocked_reasons


def test_low_data_quality_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, data_quality_score=50.0)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.LOW_DATA_QUALITY in result.blocked_reasons


def test_max_trades_reached_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, trades_today=3, max_trades_day=3)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.MAX_TRADES_REACHED in result.blocked_reasons


def test_daily_risk_exceeded_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, daily_pnl_r=-5.0)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.DAILY_RISK_EXCEEDED in result.blocked_reasons


def test_prop_breach_too_close_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, distance_to_prop_breach_r=0.1)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.PROP_BREACH_TOO_CLOSE in result.blocked_reasons
    assert result.prop_risk_valid is False


def test_model_uncertainty_too_high_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, model_uncertainty=0.9)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.MODEL_UNCERTAINTY_TOO_HIGH in result.blocked_reasons


def test_required_options_data_unavailable_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, required_options_metrics=("gex", "vomma"), available_options_metrics=("gex",))
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.REQUIRED_OPTIONS_DATA_UNAVAILABLE in result.blocked_reasons


def test_execution_quality_too_low_blocks():
    from dataclasses import replace
    state = replace(_GOOD_STATE, execution_quality_score=0.1)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.EXECUTION_QUALITY_TOO_LOW in result.blocked_reasons


def test_thresholds_are_configurable_not_hardcoded():
    from dataclasses import replace
    state = replace(_GOOD_STATE, alpha_ev_per_day=10.0)
    strict = NoTradeThresholds(min_alpha_ev_per_day=100.0)
    result = evaluate_trade_eligibility(state, strict)
    assert NoTradeReason.NO_EDGE in result.blocked_reasons

    lenient = NoTradeThresholds(min_alpha_ev_per_day=-1000.0)
    result2 = evaluate_trade_eligibility(state, lenient)
    assert NoTradeReason.NO_EDGE not in result2.blocked_reasons


def test_multiple_blocking_reasons_all_reported():
    state = TradeState(alpha_ev_per_day=-5.0, data_quality_score=10.0, trades_today=5, max_trades_day=3)
    result = evaluate_trade_eligibility(state)
    assert NoTradeReason.NO_EDGE in result.blocked_reasons
    assert NoTradeReason.LOW_DATA_QUALITY in result.blocked_reasons
    assert NoTradeReason.MAX_TRADES_REACHED in result.blocked_reasons
    assert len(result.reasons) >= 3
