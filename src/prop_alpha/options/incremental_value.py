"""Options Incremental Alpha Score (extension spec §70, tying together
§39's Incremental Information Test and §40's Options Value Test): scores
whether adding options-derived features/context to an alpha was actually
worth it, reduced to one number and a recommendation.

Rewards OOS EV improvement, OOS stability, calibration improvement,
drawdown improvement, and Payout Utility improvement (§70's own list);
penalizes complexity, data dependency, latency sensitivity, and provider
dependency (also §70) — a large raw EV delta from an unstable,
heavily provider-dependent enhancement should not score as a clear win.

This is a transparent, first-pass weighted heuristic, not a fitted or
validated scoring model — there is no labeled dataset of "was this
enhancement actually worth it" to calibrate against. Treat `score` as a
decision aid to read alongside its component breakdown, not a verdict on
its own (extension §128's own principle, applied here to a feature-value
decision rather than a live-trading one).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IncrementalValueInputs:
    baseline_oos_ev_per_day: float
    enhanced_oos_ev_per_day: float
    baseline_wf_positive_fold_fraction: float | None = None
    enhanced_wf_positive_fold_fraction: float | None = None
    baseline_calibration_brier: float | None = None
    enhanced_calibration_brier: float | None = None
    baseline_max_drawdown: float | None = None
    enhanced_max_drawdown: float | None = None
    baseline_expected_payout: float | None = None
    enhanced_expected_payout: float | None = None
    complexity_penalty: float = 0.0
    data_dependency_penalty: float = 0.0
    latency_sensitivity_penalty: float = 0.0
    provider_dependency_penalty: float = 0.0


@dataclass(frozen=True)
class IncrementalValueScore:
    ev_improvement: float
    stability_improvement: float | None
    calibration_improvement: float | None
    drawdown_improvement: float | None
    payout_utility_improvement: float | None
    total_penalty: float
    score: float
    recommendation: str


def compute_incremental_value_score(inputs: IncrementalValueInputs) -> IncrementalValueScore:
    ev_improvement = inputs.enhanced_oos_ev_per_day - inputs.baseline_oos_ev_per_day

    stability_improvement = None
    if inputs.baseline_wf_positive_fold_fraction is not None and inputs.enhanced_wf_positive_fold_fraction is not None:
        stability_improvement = inputs.enhanced_wf_positive_fold_fraction - inputs.baseline_wf_positive_fold_fraction

    calibration_improvement = None
    if inputs.baseline_calibration_brier is not None and inputs.enhanced_calibration_brier is not None:
        # Brier score: lower is better, so improvement is baseline minus enhanced.
        calibration_improvement = inputs.baseline_calibration_brier - inputs.enhanced_calibration_brier

    drawdown_improvement = None
    if inputs.baseline_max_drawdown is not None and inputs.enhanced_max_drawdown is not None:
        # Compare magnitudes: a smaller drawdown magnitude is the improvement,
        # regardless of whether drawdown is reported as negative or positive.
        drawdown_improvement = abs(inputs.baseline_max_drawdown) - abs(inputs.enhanced_max_drawdown)

    payout_utility_improvement = None
    if inputs.baseline_expected_payout is not None and inputs.enhanced_expected_payout is not None:
        payout_utility_improvement = inputs.enhanced_expected_payout - inputs.baseline_expected_payout

    total_penalty = (
        inputs.complexity_penalty + inputs.data_dependency_penalty
        + inputs.latency_sensitivity_penalty + inputs.provider_dependency_penalty
    )

    signals = [1.0 if ev_improvement > 0 else -1.0]
    for improvement in (stability_improvement, calibration_improvement, drawdown_improvement, payout_utility_improvement):
        if improvement is not None:
            signals.append(1.0 if improvement > 0 else -1.0)
    score = sum(signals) - total_penalty

    if ev_improvement <= 0:
        # extension §40: "Does it add predictive/economic value? ... Se la
        # risposta è no: FEATURE = NON-ESSENTIAL" — a non-positive EV
        # delta is disqualifying regardless of every other signal.
        recommendation = "NON_ESSENTIAL"
    elif score > 0:
        recommendation = "INCREMENTAL_VALUE_CONFIRMED"
    else:
        recommendation = "MARGINAL_OR_UNSTABLE"

    return IncrementalValueScore(
        ev_improvement=ev_improvement,
        stability_improvement=stability_improvement,
        calibration_improvement=calibration_improvement,
        drawdown_improvement=drawdown_improvement,
        payout_utility_improvement=payout_utility_improvement,
        total_penalty=total_penalty,
        score=score,
        recommendation=recommendation,
    )
