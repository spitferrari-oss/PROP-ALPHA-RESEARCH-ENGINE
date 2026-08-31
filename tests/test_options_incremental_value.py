import pytest

from prop_alpha.options.incremental_value import IncrementalValueInputs, compute_incremental_value_score


def test_positive_ev_delta_with_all_improvements_confirms_value():
    inputs = IncrementalValueInputs(
        baseline_oos_ev_per_day=100.0, enhanced_oos_ev_per_day=150.0,
        baseline_wf_positive_fold_fraction=0.6, enhanced_wf_positive_fold_fraction=0.8,
        baseline_calibration_brier=0.25, enhanced_calibration_brier=0.20,
        baseline_max_drawdown=-5000.0, enhanced_max_drawdown=-3000.0,
        baseline_expected_payout=1000.0, enhanced_expected_payout=1500.0,
    )
    result = compute_incremental_value_score(inputs)
    assert result.ev_improvement == 50.0
    assert result.stability_improvement == pytest.approx(0.2, abs=1e-9)
    assert result.calibration_improvement == pytest.approx(0.05, abs=1e-9)
    assert result.drawdown_improvement == 2000.0
    assert result.payout_utility_improvement == 500.0
    assert result.recommendation == "INCREMENTAL_VALUE_CONFIRMED"


def test_non_positive_ev_delta_is_always_non_essential_even_with_other_improvements():
    inputs = IncrementalValueInputs(
        baseline_oos_ev_per_day=100.0, enhanced_oos_ev_per_day=90.0,
        baseline_wf_positive_fold_fraction=0.5, enhanced_wf_positive_fold_fraction=0.9,
    )
    result = compute_incremental_value_score(inputs)
    assert result.recommendation == "NON_ESSENTIAL"


def test_high_penalty_can_flip_a_positive_ev_delta_to_marginal():
    inputs = IncrementalValueInputs(
        baseline_oos_ev_per_day=100.0, enhanced_oos_ev_per_day=101.0,  # tiny improvement
        complexity_penalty=1.0, data_dependency_penalty=1.0,
        latency_sensitivity_penalty=1.0, provider_dependency_penalty=1.0,
    )
    result = compute_incremental_value_score(inputs)
    assert result.total_penalty == 4.0
    assert result.recommendation == "MARGINAL_OR_UNSTABLE"


def test_missing_optional_inputs_leave_those_improvements_none():
    inputs = IncrementalValueInputs(baseline_oos_ev_per_day=100.0, enhanced_oos_ev_per_day=150.0)
    result = compute_incremental_value_score(inputs)
    assert result.stability_improvement is None
    assert result.calibration_improvement is None
    assert result.drawdown_improvement is None
    assert result.payout_utility_improvement is None
    assert result.recommendation == "INCREMENTAL_VALUE_CONFIRMED"


def test_zero_penalty_default():
    inputs = IncrementalValueInputs(baseline_oos_ev_per_day=100.0, enhanced_oos_ev_per_day=150.0)
    result = compute_incremental_value_score(inputs)
    assert result.total_penalty == 0.0
