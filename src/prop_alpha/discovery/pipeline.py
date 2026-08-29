"""Alpha Discovery Engine orchestration (spec §18/§19 Level 2, §20, §48):
generate candidates -> quick-screen each -> log every one (survivor or not)
to the Hypothesis Ledger -> run a complementary symbolic-regression scan ->
return ranked results for reporting.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.config import EngineConfig
from prop_alpha.discovery.conditions import CONDITION_LIBRARY
from prop_alpha.discovery.hypothesis import Hypothesis, HypothesisLedger
from prop_alpha.discovery.screening import quick_evaluate
from prop_alpha.discovery.setup_generator import generate_candidate_setups
from prop_alpha.discovery.symbolic_regression import compute_forward_return, symbolic_search

SYMBOLIC_REGRESSION_FEATURES = [
    "returns", "log_returns", "atr_14", "volume_z", "relative_volume",
    "realized_vol_20", "volatility_percentile", "vwap_distance", "vwap_z",
    "delta", "delta_acceleration_z", "vp_dist_to_prior_poc",
]


def _hypothesis_from_candidate(candidate, result: dict, market: str, dataset_note: str) -> Hypothesis:
    cond_names = [c.name for c in candidate.conditions]
    regimes = sorted({c.regime_hint for c in candidate.conditions if c.regime_hint}) or ["ALL"]
    direction_word = "up" if candidate.direction == 1 else "down"

    return Hypothesis(
        hypothesis_id=candidate.meta.alpha_id,
        date=dt.date.today().isoformat(),
        author="discovery_engine.combinatorial_search",
        market=market,
        mechanism=candidate.meta.mechanism,
        hypothesis=f"When {' AND '.join(cond_names)}, {market} tends to move {direction_word} "
                    f"over the following bars.",
        economic_rationale=candidate.meta.mechanism,
        expected_behavior=f"Positive EV/day in the {'-' if candidate.direction == -1 else ''}direction "
                           f"implied by the condition set, conditional on the regimes it fires in.",
        features=cond_names,
        expected_regimes=regimes,
        expected_failure_modes=["REGIME_FRAGILE", "LOW_SAMPLE", "HIGH_COST", "PARAMETER_FRAGILE"],
        test_plan=f"Combinatorial IS/OOS quick screen on {dataset_note} (spec §18/§19 Level 2); "
                  f"promotion to WALK_FORWARD/ROBUST requires the full Phase 4 gates via "
                  f"`pae research full-run`.",
        result=f"n_trades={result['n_trades']}, IS EV/day={result['is_ev_per_day']:.2f}, "
                f"OOS EV/day={result['oos_ev_per_day']:.2f}" if result["n_trades"] > 0
                else "n_trades=0 (condition combination never fired)",
        status="BACKTESTED" if result["passed_screen"] else "RETIRED",
    )


def run_discovery(
    df_feat: pd.DataFrame,
    cost_model: CostModel,
    config: EngineConfig,
    oos_start_day,
    ledger: HypothesisLedger | None = None,
    dataset_note: str = "synthetic demo dataset",
) -> dict:
    ledger = ledger or HypothesisLedger()

    candidates = generate_candidate_setups(
        CONDITION_LIBRARY,
        max_combo_size=config.discovery.max_combo_size,
        max_candidates=config.discovery.max_candidates,
        seed=config.seed,
    )

    results = []
    hypotheses = []
    for candidate in candidates:
        result = quick_evaluate(candidate, df_feat, cost_model, config, oos_start_day)
        results.append(result)
        hypotheses.append(_hypothesis_from_candidate(candidate, result, config.market.symbol, dataset_note))

    ledger.append_many(hypotheses)

    survivors = sorted(
        (r for r in results if r["passed_screen"]),
        key=lambda r: -r["oos_ev_per_day"],
    )

    forward_return = compute_forward_return(df_feat, config.discovery.symbolic_regression_horizon_bars)
    available_features = [f for f in SYMBOLIC_REGRESSION_FEATURES if f in df_feat.columns]
    symbolic_results = symbolic_search(
        df_feat, available_features, forward_return,
        top_k=config.discovery.symbolic_regression_top_k,
        min_obs=config.discovery.symbolic_regression_min_obs,
    )

    return {
        "n_candidates": len(candidates),
        "n_passed_screen": len(survivors),
        "survivors": survivors,
        "all_results": results,
        "symbolic_results": symbolic_results,
        "ledger_path": str(ledger.path),
    }
