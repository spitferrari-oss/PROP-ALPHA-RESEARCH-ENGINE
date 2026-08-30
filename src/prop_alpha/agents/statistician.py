"""Statistician Agent (spec §58): mechanically checks the Research Gates
(spec §60) that already-computed evidence from Phases 1-8 can answer.
Never judges by "looks good" — every gate reads a specific field already
produced by the backtest/statistics/prop pipeline, or is marked
NOT_EVALUATED when no engine exists yet to answer it (spec §128: the
system must not quietly treat an unchecked criterion as satisfied).
"""
from __future__ import annotations

from prop_alpha.agents.gates import Gate
from prop_alpha.config import AgentsConfig


def evaluate_statistician_gates(
    alpha_result: dict,
    config: AgentsConfig | None = None,
    paper_monitor_result: dict | None = None,
    decay_result: dict | None = None,
) -> list[Gate]:
    config = config or AgentsConfig()
    gates: list[Gate] = []

    # GATE 1 — Data valid: structural. Reaching this point at all means the
    # data quality gate earlier in the pipeline already passed (cli aborts
    # with BACKTEST STATUS = INVALID otherwise), so this is a true pass,
    # not an assumption.
    gates.append(Gate("DATA_VALID", "PASS", "Data quality gate passed upstream of this evaluation."))

    # GATE 2 — No leakage: no dedicated leakage engine exists yet (spec §28).
    gates.append(Gate("NO_LEAKAGE", "NOT_EVALUATED",
                       "No dedicated data-leakage engine (spec §28) — only the no-look-ahead "
                       "discipline built into the feature/backtest code, not actively tested."))

    # GATE 3 — Economic/statistical hypothesis coherent.
    mechanism = (alpha_result.get("mechanism") or "").strip()
    gates.append(Gate(
        "HYPOTHESIS_COHERENT",
        "PASS" if mechanism else "FAIL",
        f"mechanism='{mechanism}'" if mechanism else "AlphaMeta.mechanism is empty",
    ))

    # GATE 4 — Sufficient sample.
    n_trades = alpha_result.get("n_trades", 0) or 0
    gates.append(Gate(
        "SUFFICIENT_SAMPLE",
        "PASS" if n_trades >= config.min_trades_for_sample_gate else "FAIL",
        f"n_trades={n_trades} (threshold={config.min_trades_for_sample_gate})",
    ))

    # GATE 5 — Positive OOS.
    research_status = alpha_result.get("research_status", "BACKTESTED")
    oos_positive = research_status in ("OUT_OF_SAMPLE", "WALK_FORWARD")
    gates.append(Gate("POSITIVE_OOS", "PASS" if oos_positive else "FAIL",
                       f"research_status={research_status}"))

    # GATE 6 — Walk-forward robust. `diagnostics_run` is False when the run
    # used `--fast` (walk-forward/cost-sensitivity skipped entirely) — that
    # must read as NOT_EVALUATED, never as FAIL; a gate can only fail a
    # check that was actually run.
    diagnostics_run = alpha_result.get("diagnostics_run", False)
    wf_fraction = alpha_result.get("wf_positive_fold_fraction")
    if not diagnostics_run:
        gates.append(Gate("WALK_FORWARD_ROBUST", "NOT_EVALUATED",
                           "Walk-forward analysis was not run this pass (e.g. `--fast`)."))
    else:
        wf_robust = research_status == "WALK_FORWARD"
        gates.append(Gate(
            "WALK_FORWARD_ROBUST", "PASS" if wf_robust else "FAIL",
            f"research_status={research_status}, positive_fold_fraction={wf_fraction}",
        ))

    # GATE 7 — Cost robust: survives at least base costs, not only optimistic.
    breakeven = alpha_result.get("breakeven_cost_profile")
    if not diagnostics_run:
        gates.append(Gate("COST_ROBUST", "NOT_EVALUATED",
                           "Cost-sensitivity sweep was not run this pass (e.g. `--fast`)."))
    else:
        cost_robust = breakeven in ("base", "conservative", "stress", "extreme")
        gates.append(Gate("COST_ROBUST", "PASS" if cost_robust else "FAIL",
                           f"breakeven_cost_profile={breakeven}"))

    # GATE 8 — Parameter robust: no parameter-sensitivity sweep exists yet (spec §70).
    gates.append(Gate("PARAMETER_ROBUST", "NOT_EVALUATED",
                       "No parameter-sensitivity surface (spec §70) — not swept."))

    # GATE 9 — Regime robustness is delegated to the Critic Agent's
    # REGIME_FRAGILE finding (statistician.py doesn't have the per-regime
    # breakdown); the Supervisor merges it in.

    # GATE 10 — Monte Carlo acceptable (breach probability).
    p_breach = alpha_result.get("p_breach")
    mc_ok = p_breach is not None and p_breach == p_breach and p_breach <= config.max_acceptable_p_breach
    gates.append(Gate("MONTE_CARLO_ACCEPTABLE", "PASS" if mc_ok else "FAIL",
                       f"p_breach={p_breach} (threshold<={config.max_acceptable_p_breach})"))

    # GATE 11 — Prop survival acceptable (payout probability).
    p_payout = alpha_result.get("p_payout")
    prop_ok = p_payout is not None and p_payout == p_payout and p_payout >= config.min_acceptable_p_payout
    gates.append(Gate("PROP_SURVIVAL_ACCEPTABLE", "PASS" if prop_ok else "FAIL",
                       f"p_payout={p_payout} (threshold>={config.min_acceptable_p_payout})"))

    # GATE 12 — Paper trading acceptable (spec §132, §98): the shadow log
    # replays the OOS holdout (see paper/shadow.py) — NOT_EVALUATED when
    # there's nothing to replay yet, otherwise PASS only for a GREEN decay
    # classification (spec §133's live-eligibility bar is strict: YELLOW/
    # ORANGE/RED all mean an unresolved concern, not a pass).
    if paper_monitor_result is None or paper_monitor_result.get("status") != "OK" or decay_result is None:
        gates.append(Gate("PAPER_TRADING_ACCEPTABLE", "NOT_EVALUATED",
                           "No shadow-mode trades available this pass (paper monitor not run or empty)."))
    else:
        level = decay_result.get("level")
        paper_ok = level == "GREEN"
        gates.append(Gate(
            "PAPER_TRADING_ACCEPTABLE", "PASS" if paper_ok else "FAIL",
            f"shadow decay level={level} over {decay_result.get('n_shadow_days', 0)} shadow days "
            f"({decay_result.get('reason', '')})",
        ))

    return gates
