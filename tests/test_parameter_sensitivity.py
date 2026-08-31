import pytest

from prop_alpha.statistics.parameter_sensitivity import (
    ParameterSpec,
    grid_sensitivity,
    local_perturbation,
)


def test_local_perturbation_default_points_are_base_and_pct_bounds():
    spec = ParameterSpec(name="stop_atr_mult", base_value=2.0, perturbation_pct=0.1)
    assert spec.points() == pytest.approx([1.8, 2.0, 2.2])


def test_local_perturbation_explicit_grid_overrides_pct():
    spec = ParameterSpec(name="x", base_value=2.0, grid_values=(1.0, 2.0, 3.0, 4.0))
    assert spec.points() == [1.0, 2.0, 3.0, 4.0]


def test_local_perturbation_zero_base_value_yields_single_point():
    spec = ParameterSpec(name="x", base_value=0.0)
    assert spec.points() == [0.0]


def test_local_perturbation_stable_strategy_high_stability_score():
    # metric barely moves across the neighborhood -> high stability
    def evaluate(params):
        return 100.0 + params["x"] * 0.01

    result = local_perturbation(ParameterSpec(name="x", base_value=10.0, perturbation_pct=0.1), evaluate)
    assert result.stability_score == pytest.approx(1.0)


def test_local_perturbation_unstable_strategy_low_stability_score():
    # metric flips sign entirely as x moves -> low stability
    def evaluate(params):
        return 100.0 if params["x"] == 10.0 else -500.0

    result = local_perturbation(ParameterSpec(name="x", base_value=10.0, perturbation_pct=0.1), evaluate)
    assert result.stability_score < 1.0


def test_grid_sensitivity_evaluates_full_cartesian_product():
    def evaluate(params):
        return params["a"] + params["b"]

    specs = [
        ParameterSpec(name="a", base_value=1.0, grid_values=(0.0, 1.0)),
        ParameterSpec(name="b", base_value=1.0, grid_values=(0.0, 1.0)),
    ]
    result = grid_sensitivity(specs, evaluate)
    assert len(result.points) == 4


def test_grid_sensitivity_best_and_worst_points():
    def evaluate(params):
        return params["a"]

    specs = [ParameterSpec(name="a", base_value=2.0, grid_values=(1.0, 2.0, 3.0))]
    result = grid_sensitivity(specs, evaluate)
    assert result.best_point.metric_value == 3.0
    assert result.worst_point.metric_value == 1.0


def test_grid_sensitivity_none_metric_values_excluded_from_evaluated_points():
    def evaluate(params):
        return None if params["a"] == 2.0 else params["a"]

    specs = [ParameterSpec(name="a", base_value=2.0, grid_values=(1.0, 2.0, 3.0))]
    result = grid_sensitivity(specs, evaluate)
    assert len(result.points) == 3
    assert len(result.evaluated_points()) == 2


def test_grid_sensitivity_empty_specs_raises():
    with pytest.raises(ValueError, match="at least one"):
        grid_sensitivity([], lambda params: 1.0)


def test_grid_sensitivity_records_base_params_and_base_metric():
    def evaluate(params):
        return params["a"] * 2

    specs = [ParameterSpec(name="a", base_value=5.0, grid_values=(4.0, 5.0, 6.0))]
    result = grid_sensitivity(specs, evaluate)
    assert result.base_params == {"a": 5.0}
    assert result.base_metric_value == 10.0


def test_stability_score_none_when_base_metric_is_none():
    def evaluate(params):
        return None

    specs = [ParameterSpec(name="a", base_value=5.0, grid_values=(4.0, 5.0, 6.0))]
    result = grid_sensitivity(specs, evaluate)
    assert result.stability_score is None
    assert result.best_point is None
    assert result.worst_point is None
