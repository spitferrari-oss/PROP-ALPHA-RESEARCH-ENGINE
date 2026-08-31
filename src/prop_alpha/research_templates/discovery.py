"""Auto-generate GEX/futures templates, screen each one, and log every
candidate — survivor or not — to the Hypothesis Ledger (extension
§111-114, mirroring `discovery.pipeline.run_discovery`'s exact shape for
futures-only candidates, extension §20's "no backtest without a logged
hypothesis" applying here just as much as it does to the core engine).

Deliberately narrower than `discovery.pipeline.run_discovery`: no
symbolic-regression scan here — that is the core Discovery Engine's own
concern (Phase 7) over the futures feature set, not something this
cross-market template generator duplicates.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from prop_alpha.backtest.costs import CostModel
from prop_alpha.config import EngineConfig
from prop_alpha.discovery.conditions import Condition
from prop_alpha.discovery.hypothesis import Hypothesis, HypothesisLedger
from prop_alpha.discovery.screening import quick_evaluate
from prop_alpha.discovery.setup_generator import GeneratedStrategy
from prop_alpha.research_templates.templates import generate_gex_futures_templates


def hypothesis_from_gex_template(
    candidate: GeneratedStrategy, result: dict, market: str, dataset_note: str,
) -> Hypothesis:
    cond_names = [c.name for c in candidate.conditions]
    direction_word = "up" if candidate.direction == 1 else "down"

    return Hypothesis(
        hypothesis_id=candidate.meta.alpha_id,
        date=dt.date.today().isoformat(),
        author="research_templates.gex_futures_discovery",
        market=f"{market} (cross-market: futures + GEXBOT options)",
        mechanism=candidate.meta.mechanism,
        hypothesis=f"When {' AND '.join(cond_names)}, {market} tends to move {direction_word} "
                    f"over the following bars, conditional on the synced options/GEX state.",
        economic_rationale=candidate.meta.mechanism,
        expected_behavior=f"Positive EV/day in the {'-' if candidate.direction == -1 else ''}direction "
                           f"implied by the condition set, conditional on the GEX/DEX state it fires in — "
                           f"extension §37's No-Assumption Principle means this is exactly what needs "
                           f"testing, not something assumed true because a GEX condition is present.",
        features=cond_names,
        expected_regimes=["ALL"],
        expected_failure_modes=["REGIME_FRAGILE", "LOW_SAMPLE", "HIGH_COST", "PARAMETER_FRAGILE", "GEX_STATE_STALE"],
        test_plan=f"Combinatorial IS/OOS quick screen on {dataset_note}, synced against GEXBOT options "
                  f"state (extension §35-36); promotion requires the full Phase 4-6 gates via `pae "
                  f"research full-run`, plus `options.conditional_ev.conditional_ev_by_gex_regime` "
                  f"(extension §69) as an additional cross-market check.",
        result=f"n_trades={result['n_trades']}, IS EV/day={result['is_ev_per_day']:.2f}, "
                f"OOS EV/day={result['oos_ev_per_day']:.2f}" if result["n_trades"] > 0
                else "n_trades=0 (condition combination never fired)",
        status="BACKTESTED" if result["passed_screen"] else "RETIRED",
    )


def run_gex_futures_discovery(
    df_enriched: pd.DataFrame,
    cost_model: CostModel,
    config: EngineConfig,
    oos_start_day,
    ledger: HypothesisLedger | None = None,
    market: str = "",
    dataset_note: str = "synced futures+options dataset",
    futures_library: list[Condition] | None = None,
    gex_library: list[Condition] | None = None,
) -> dict:
    ledger = ledger or HypothesisLedger()
    market = market or config.market.symbol

    candidates = generate_gex_futures_templates(
        futures_library=futures_library, gex_library=gex_library,
        max_candidates=config.discovery.max_candidates, seed=config.seed,
    )

    results = []
    hypotheses = []
    for candidate in candidates:
        result = quick_evaluate(candidate, df_enriched, cost_model, config, oos_start_day)
        results.append(result)
        hypotheses.append(hypothesis_from_gex_template(candidate, result, market, dataset_note))

    ledger.append_many(hypotheses)

    survivors = sorted(
        (r for r in results if r["passed_screen"]),
        key=lambda r: -r["oos_ev_per_day"],
    )

    return {
        "n_candidates": len(candidates),
        "n_passed_screen": len(survivors),
        "survivors": survivors,
        "all_results": results,
    }
