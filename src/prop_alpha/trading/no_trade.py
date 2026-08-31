"""The explicit no-trade gate (hardening pass Step 5-6, Blocker E).

Governance principle `NO_TRADE_IS_DEFAULT` (`config/
research_constitution.yaml`): in the absence of a positive, currently-
valid eligibility determination, the default action is to not trade.
`evaluate_trade_eligibility` implements that literally for the two most
foundational checks — a missing/unknown expected value (`NO_EDGE`) or a
missing/unknown data-quality score (`LOW_DATA_QUALITY`) each block by
themselves, rather than being silently skipped, because "we don't know if
there's an edge" and "we don't know if the data is trustworthy" are
exactly the situations this gate exists to catch. The remaining checks
(regime, liquidity, event risk, model uncertainty, execution quality) are
refinements on top of a confirmed edge/quality baseline: when their input
isn't supplied, they contribute a `warnings` entry (visible, not hidden)
but do not by themselves flip `eligible` to `False` — forcing every one
of them to be mandatory would make the gate impossible to use anywhere
that doesn't yet have every signal wired up, which is the honest state of
this repository today. This tradeoff is deliberate and documented here,
not an oversight.

No threshold is hardcoded in this module's logic — every comparison reads
from a `NoTradeThresholds` instance, which a caller can build from
`config/research_constitution.yaml`'s `hard_gates` or its own
configuration; `NoTradeThresholds()`'s field defaults exist only so the
dataclass is usable standalone in tests, not as an implicit policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NoTradeReason(str, Enum):
    NO_EDGE = "NO_EDGE"
    BAD_REGIME = "BAD_REGIME"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    HIGH_EVENT_RISK = "HIGH_EVENT_RISK"
    STALE_REQUIRED_DATA = "STALE_REQUIRED_DATA"
    LOW_DATA_QUALITY = "LOW_DATA_QUALITY"
    MAX_TRADES_REACHED = "MAX_TRADES_REACHED"
    DAILY_RISK_EXCEEDED = "DAILY_RISK_EXCEEDED"
    PROP_BREACH_TOO_CLOSE = "PROP_BREACH_TOO_CLOSE"
    MODEL_UNCERTAINTY_TOO_HIGH = "MODEL_UNCERTAINTY_TOO_HIGH"
    REQUIRED_OPTIONS_DATA_UNAVAILABLE = "REQUIRED_OPTIONS_DATA_UNAVAILABLE"
    EXECUTION_QUALITY_TOO_LOW = "EXECUTION_QUALITY_TOO_LOW"


@dataclass(frozen=True)
class NoTradeThresholds:
    min_alpha_ev_per_day: float = 0.0
    min_liquidity_relative_volume: float = 0.3
    max_required_data_age_seconds: float = 300.0
    min_data_quality_score: float = 95.0
    max_daily_loss_r: float = 3.0
    prop_breach_buffer_r: float = 0.5
    max_model_uncertainty: float = 0.5
    min_execution_quality_score: float = 0.5


@dataclass(frozen=True)
class TradeState:
    """Real-time inputs `evaluate_trade_eligibility` needs. Every field is
    optional — a caller who doesn't have a signal yet passes `None` for
    it, never a fabricated value (extension's own MISSING_NOT_ZERO
    principle applies here as much as to any options metric).
    """
    alpha_ev_per_day: float | None = None
    regime: str | None = None
    valid_regimes: tuple[str, ...] | None = None
    relative_volume: float | None = None
    required_data_age_seconds: dict[str, float] | None = None
    data_quality_score: float | None = None
    trades_today: int = 0
    max_trades_day: int | None = None
    daily_pnl_r: float | None = None
    distance_to_prop_breach_r: float | None = None
    model_uncertainty: float | None = None
    required_options_metrics: tuple[str, ...] = ()
    available_options_metrics: tuple[str, ...] = ()
    execution_quality_score: float | None = None
    high_impact_event_within_minutes: float | None = None
    event_blackout_minutes: float | None = None


@dataclass(frozen=True)
class TradeEligibility:
    eligible: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    blocked_reasons: tuple[NoTradeReason, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    data_quality: float | None = None
    regime_valid: bool | None = None
    event_risk: bool | None = None
    liquidity_valid: bool | None = None
    alpha_ev_valid: bool | None = None
    prop_risk_valid: bool | None = None


def evaluate_trade_eligibility(
    state: TradeState, thresholds: NoTradeThresholds | None = None,
) -> TradeEligibility:
    thresholds = thresholds or NoTradeThresholds()
    blocked: list[NoTradeReason] = []
    warnings: list[str] = []
    reasons: list[str] = []

    # --- foundational: fail closed when unknown ---
    if state.alpha_ev_per_day is None:
        alpha_ev_valid = False
        blocked.append(NoTradeReason.NO_EDGE)
        reasons.append("alpha_ev_per_day not supplied — cannot confirm a positive edge")
    else:
        alpha_ev_valid = state.alpha_ev_per_day >= thresholds.min_alpha_ev_per_day
        if not alpha_ev_valid:
            blocked.append(NoTradeReason.NO_EDGE)
            reasons.append(f"alpha_ev_per_day={state.alpha_ev_per_day} < {thresholds.min_alpha_ev_per_day}")

    if state.data_quality_score is None:
        data_quality_valid = False
        blocked.append(NoTradeReason.LOW_DATA_QUALITY)
        reasons.append("data_quality_score not supplied — cannot confirm data is trustworthy")
    else:
        data_quality_valid = state.data_quality_score >= thresholds.min_data_quality_score
        if not data_quality_valid:
            blocked.append(NoTradeReason.LOW_DATA_QUALITY)
            reasons.append(f"data_quality_score={state.data_quality_score} < {thresholds.min_data_quality_score}")

    # --- refinements: warn, don't fail closed, when unknown ---
    if state.regime is None or state.valid_regimes is None:
        regime_valid = None
        warnings.append("regime not evaluated (regime or valid_regimes not supplied)")
    else:
        regime_valid = state.regime in state.valid_regimes
        if not regime_valid:
            blocked.append(NoTradeReason.BAD_REGIME)
            reasons.append(f"regime={state.regime!r} not in {state.valid_regimes}")

    if state.relative_volume is None:
        liquidity_valid = None
        warnings.append("liquidity not evaluated (relative_volume not supplied)")
    else:
        liquidity_valid = state.relative_volume >= thresholds.min_liquidity_relative_volume
        if not liquidity_valid:
            blocked.append(NoTradeReason.LOW_LIQUIDITY)
            reasons.append(f"relative_volume={state.relative_volume} < {thresholds.min_liquidity_relative_volume}")

    if state.high_impact_event_within_minutes is None or state.event_blackout_minutes is None:
        event_risk: bool | None = None
        warnings.append("event risk not evaluated (event timing not supplied)")
    else:
        event_risk = state.high_impact_event_within_minutes <= state.event_blackout_minutes
        if event_risk:
            blocked.append(NoTradeReason.HIGH_EVENT_RISK)
            reasons.append(
                f"high-impact event in {state.high_impact_event_within_minutes}min "
                f"<= {state.event_blackout_minutes}min blackout"
            )

    if state.required_data_age_seconds is None:
        warnings.append("data freshness not evaluated (required_data_age_seconds not supplied)")
    else:
        stale = {
            name: age for name, age in state.required_data_age_seconds.items()
            if age > thresholds.max_required_data_age_seconds
        }
        if stale:
            blocked.append(NoTradeReason.STALE_REQUIRED_DATA)
            reasons.append(f"stale required data: {stale}")

    if state.max_trades_day is not None and state.trades_today >= state.max_trades_day:
        blocked.append(NoTradeReason.MAX_TRADES_REACHED)
        reasons.append(f"trades_today={state.trades_today} >= max_trades_day={state.max_trades_day}")

    if state.daily_pnl_r is not None and state.daily_pnl_r <= -thresholds.max_daily_loss_r:
        blocked.append(NoTradeReason.DAILY_RISK_EXCEEDED)
        reasons.append(f"daily_pnl_r={state.daily_pnl_r} <= -{thresholds.max_daily_loss_r}")

    if state.distance_to_prop_breach_r is None:
        prop_risk_valid: bool | None = None
        warnings.append("prop breach distance not evaluated (distance_to_prop_breach_r not supplied)")
    else:
        prop_risk_valid = state.distance_to_prop_breach_r > thresholds.prop_breach_buffer_r
        if not prop_risk_valid:
            blocked.append(NoTradeReason.PROP_BREACH_TOO_CLOSE)
            reasons.append(
                f"distance_to_prop_breach_r={state.distance_to_prop_breach_r} <= {thresholds.prop_breach_buffer_r}"
            )

    if state.model_uncertainty is not None and state.model_uncertainty > thresholds.max_model_uncertainty:
        blocked.append(NoTradeReason.MODEL_UNCERTAINTY_TOO_HIGH)
        reasons.append(f"model_uncertainty={state.model_uncertainty} > {thresholds.max_model_uncertainty}")

    if state.required_options_metrics:
        missing = set(state.required_options_metrics) - set(state.available_options_metrics)
        if missing:
            blocked.append(NoTradeReason.REQUIRED_OPTIONS_DATA_UNAVAILABLE)
            reasons.append(f"required options metrics unavailable: {sorted(missing)}")

    if state.execution_quality_score is not None and state.execution_quality_score < thresholds.min_execution_quality_score:
        blocked.append(NoTradeReason.EXECUTION_QUALITY_TOO_LOW)
        reasons.append(
            f"execution_quality_score={state.execution_quality_score} < {thresholds.min_execution_quality_score}"
        )

    return TradeEligibility(
        eligible=len(blocked) == 0,
        reasons=tuple(reasons),
        blocked_reasons=tuple(blocked),
        warnings=tuple(warnings),
        data_quality=state.data_quality_score,
        regime_valid=regime_valid,
        event_risk=event_risk,
        liquidity_valid=liquidity_valid,
        alpha_ev_valid=alpha_ev_valid,
        prop_risk_valid=prop_risk_valid,
    )


def should_trade(state: TradeState, thresholds: NoTradeThresholds | None = None) -> bool:
    return evaluate_trade_eligibility(state, thresholds).eligible
