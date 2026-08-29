"""Payout Optimizer (spec §38): compares named sizing/stop-trading policies
by **Expected Payout**, not raw return — the whole point of §38 is that the
policy maximizing account balance growth is not necessarily the one that
maximizes E[Payout] under prop constraints (a policy that also survives
daily-loss/trailing-DD gates more often can out-earn a higher-return policy
that breaches more often).

The five default policies are the spec's own worked examples: constant
risk, risk that scales up after an intraday profit, risk that scales down
after an intraday loss, an early profit lock, and a later stop-after-+XR.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.backtest.metrics import compute_day_metrics, daily_pnl
from prop_alpha.config import PropFirmConfig
from prop_alpha.prop.simulator import simulate_prop_paths
from prop_alpha.risk.position_sizing import SizingConfig, apply_position_sizing
from prop_alpha.risk.stop_trading import StopTradingPolicy, apply_day_policy
from prop_alpha.statistics.monte_carlo import simulate_daily_pnl_paths


def default_policies(base_risk_per_trade_pct: float = 0.005) -> list[tuple[str, SizingConfig, StopTradingPolicy]]:
    return [
        ("A_constant_risk", SizingConfig(risk_per_trade_pct=base_risk_per_trade_pct),
         StopTradingPolicy(name="A_constant_risk")),
        ("B_increase_after_profit", SizingConfig(risk_per_trade_pct=base_risk_per_trade_pct,
                                                  dynamic_rule="increase_after_profit"),
         StopTradingPolicy(name="B_increase_after_profit")),
        ("C_decrease_after_loss", SizingConfig(risk_per_trade_pct=base_risk_per_trade_pct,
                                                dynamic_rule="decrease_after_loss"),
         StopTradingPolicy(name="C_decrease_after_loss")),
        ("D_profit_lock_1R", SizingConfig(risk_per_trade_pct=base_risk_per_trade_pct),
         StopTradingPolicy(name="D_profit_lock_1R", stop_after_profit_r=1.0)),
        ("E_stop_after_2R", SizingConfig(risk_per_trade_pct=base_risk_per_trade_pct),
         StopTradingPolicy(name="E_stop_after_2R", stop_after_profit_r=2.0)),
    ]


def compare_policies(
    trades_df: pd.DataFrame,
    prop: PropFirmConfig,
    point_value: float,
    seed: int = 42,
    n_paths: int = 5000,
    n_days: int = 30,
    policies: list[tuple[str, SizingConfig, StopTradingPolicy]] | None = None,
) -> list[dict]:
    policies = policies if policies is not None else default_policies()
    results = []
    for name, sizing_config, stop_policy in policies:
        filtered = apply_day_policy(trades_df, stop_policy)
        sized = apply_position_sizing(filtered, sizing_config, prop, point_value)

        day_metrics = compute_day_metrics(sized)
        dpnl = daily_pnl(sized)

        mc_paths = simulate_daily_pnl_paths(dpnl, n_paths=n_paths, n_days=n_days, seed=seed) if len(dpnl) > 1 else None
        prop_sim = (
            simulate_prop_paths(mc_paths, prop)
            if mc_paths is not None
            else {"p_breach": float("nan"), "p_payout": float("nan"), "expected_payout": float("nan"),
                  "expected_days_to_payout": float("nan")}
        )

        results.append({
            "policy_name": name,
            "description": stop_policy.describe(),
            "sizing_method": sizing_config.method,
            "dynamic_rule": sizing_config.dynamic_rule,
            "n_trades": int((sized["contracts"] > 0).sum()) if not sized.empty else 0,
            "avg_contracts": float(sized.loc[sized["contracts"] > 0, "contracts"].mean()) if not sized.empty and (sized["contracts"] > 0).any() else 0.0,
            "ev_per_day_dollars": day_metrics["ev_per_day_dollars"],
            "max_drawdown": day_metrics["max_drawdown"],
            "p_breach": prop_sim["p_breach"],
            "p_payout": prop_sim["p_payout"],
            "expected_payout": prop_sim["expected_payout"],
            "expected_days_to_payout": prop_sim["expected_days_to_payout"],
        })
    return results


def rank_policies_by_expected_payout(results: list[dict]) -> list[dict]:
    def sort_key(r: dict) -> tuple[float, float]:
        payout = r["expected_payout"]
        breach = r["p_breach"]
        return (
            -payout if payout == payout else float("inf"),  # NaN sorts last
            breach if breach == breach else float("inf"),
        )

    return sorted(results, key=sort_key)
