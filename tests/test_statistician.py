from prop_alpha.agents.statistician import evaluate_statistician_gates
from prop_alpha.config import AgentsConfig


def _good_alpha_result(**overrides):
    base = dict(
        mechanism="Trend persistence following directional order flow",
        n_trades=200,
        research_status="WALK_FORWARD",
        diagnostics_run=True,
        wf_positive_fold_fraction=0.8,
        breakeven_cost_profile="stress",
        p_breach=0.05,
        p_payout=0.7,
    )
    base.update(overrides)
    return base


def _gate_by_name(gates, name):
    return next(g for g in gates if g.name == name)


def test_all_evaluable_gates_pass_for_strong_alpha():
    gates = evaluate_statistician_gates(_good_alpha_result())
    evaluated = [g for g in gates if g.status != "NOT_EVALUATED"]
    assert all(g.status == "PASS" for g in evaluated)


def test_not_evaluated_gates_present_and_distinct_from_fail():
    gates = evaluate_statistician_gates(_good_alpha_result())
    statuses = {g.name: g.status for g in gates}
    assert statuses["NO_LEAKAGE"] == "NOT_EVALUATED"
    assert statuses["PARAMETER_ROBUST"] == "NOT_EVALUATED"
    assert statuses["PAPER_TRADING_ACCEPTABLE"] == "NOT_EVALUATED"


def test_hypothesis_coherent_fails_on_empty_mechanism():
    gates = evaluate_statistician_gates(_good_alpha_result(mechanism=""))
    assert _gate_by_name(gates, "HYPOTHESIS_COHERENT").status == "FAIL"


def test_sufficient_sample_respects_config_threshold():
    gates = evaluate_statistician_gates(_good_alpha_result(n_trades=50), AgentsConfig(min_trades_for_sample_gate=100))
    assert _gate_by_name(gates, "SUFFICIENT_SAMPLE").status == "FAIL"

    gates2 = evaluate_statistician_gates(_good_alpha_result(n_trades=150), AgentsConfig(min_trades_for_sample_gate=100))
    assert _gate_by_name(gates2, "SUFFICIENT_SAMPLE").status == "PASS"


def test_positive_oos_fails_when_backtested_only():
    gates = evaluate_statistician_gates(_good_alpha_result(research_status="BACKTESTED"))
    assert _gate_by_name(gates, "POSITIVE_OOS").status == "FAIL"
    assert _gate_by_name(gates, "WALK_FORWARD_ROBUST").status == "FAIL"


def test_out_of_sample_passes_oos_but_not_walk_forward():
    gates = evaluate_statistician_gates(_good_alpha_result(research_status="OUT_OF_SAMPLE"))
    assert _gate_by_name(gates, "POSITIVE_OOS").status == "PASS"
    assert _gate_by_name(gates, "WALK_FORWARD_ROBUST").status == "FAIL"


def test_cost_robust_fails_for_optimistic_only_or_none():
    gates = evaluate_statistician_gates(_good_alpha_result(breakeven_cost_profile="optimistic"))
    assert _gate_by_name(gates, "COST_ROBUST").status == "FAIL"
    gates2 = evaluate_statistician_gates(_good_alpha_result(breakeven_cost_profile=None))
    assert _gate_by_name(gates2, "COST_ROBUST").status == "FAIL"


def test_monte_carlo_and_prop_survival_respect_thresholds():
    config = AgentsConfig(max_acceptable_p_breach=0.1, min_acceptable_p_payout=0.5)
    gates = evaluate_statistician_gates(_good_alpha_result(p_breach=0.15, p_payout=0.3), config)
    assert _gate_by_name(gates, "MONTE_CARLO_ACCEPTABLE").status == "FAIL"
    assert _gate_by_name(gates, "PROP_SURVIVAL_ACCEPTABLE").status == "FAIL"


def test_nan_p_breach_does_not_pass():
    gates = evaluate_statistician_gates(_good_alpha_result(p_breach=float("nan")))
    assert _gate_by_name(gates, "MONTE_CARLO_ACCEPTABLE").status == "FAIL"


def test_diagnostics_not_run_marks_wf_and_cost_gates_not_evaluated_not_fail():
    # e.g. `--fast` mode: walk-forward/cost-sensitivity were never computed.
    # These gates must read NOT_EVALUATED, never FAIL — a gate can only
    # fail a check that actually ran.
    gates = evaluate_statistician_gates(_good_alpha_result(diagnostics_run=False))
    assert _gate_by_name(gates, "WALK_FORWARD_ROBUST").status == "NOT_EVALUATED"
    assert _gate_by_name(gates, "COST_ROBUST").status == "NOT_EVALUATED"
