"""Cost sensitivity / slippage stress test (spec §23, §24).

Re-backtests a strategy's already-generated signals under each cost profile
in `backtest.costs.COST_PROFILES` (optimistic -> extreme) and reports the
EV/day degradation curve. A strategy whose edge only survives at optimistic
costs is fragile — it should be penalized relative to one that stays
profitable under stress costs (spec §23: "una strategia che funziona
soltanto in condizioni di costi perfette deve essere penalizzata").
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.backtest.costs import COST_PROFILES, CostModel
from prop_alpha.backtest.engine import run_backtest, trades_to_frame
from prop_alpha.backtest.metrics import compute_day_metrics


def evaluate_cost_sensitivity(
    df_signals: pd.DataFrame,
    base_cost_model: CostModel,
    max_trades_day: int,
    point_value: float,
) -> dict[str, float]:
    """`df_signals` must already carry direction/stop_distance/target_distance
    (i.e. it's the output of Strategy.with_risk_levels) so signal generation
    is not repeated per cost profile.
    """
    ev_per_day_by_profile = {}
    for profile in COST_PROFILES:
        cost_model = base_cost_model.scaled(profile)
        trades = run_backtest(df_signals, cost_model, max_trades_day=max_trades_day, point_value=point_value)
        trades_df = trades_to_frame(trades)
        metrics = compute_day_metrics(trades_df)
        ev_per_day_by_profile[profile] = metrics["ev_per_day_dollars"]
    return ev_per_day_by_profile


def breakeven_cost_profile(ev_per_day_by_profile: dict[str, float]) -> str | None:
    """The most expensive profile (in COST_PROFILES order) at which EV/day
    is still non-negative — a quick, coarse read on the strategy's cost
    margin of safety (a finer breakeven commission is spec §104).
    """
    survivors = [p for p in COST_PROFILES if ev_per_day_by_profile.get(p, float("-inf")) is not None
                 and ev_per_day_by_profile.get(p, float("-inf")) >= 0]
    return survivors[-1] if survivors else None
