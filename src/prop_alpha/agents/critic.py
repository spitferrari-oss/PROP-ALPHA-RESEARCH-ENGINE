"""Critic / Adversarial Agent (spec §59): for the apparently-winning
alpha, actively try to find reasons it might be false — low sample,
overfitting, regime-specific accident, execution sensitivity, hidden
correlation with a trivial baseline. Findings are informational, not
gates: the Supervisor decides how much weight to give them (a HIGH
severity finding blocks the verdict; LOW/MEDIUM do not, but are always
surfaced).
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.agents.gates import Finding
from prop_alpha.config import AgentsConfig
from prop_alpha.statistics.pbo import build_pnl_matrix


def evaluate_critic_findings(
    alpha_result: dict,
    pbo_result: dict | None,
    conditional_ev_table: pd.DataFrame | None,
    alpha_daily_pnl: pd.Series | None,
    baseline_daily_pnl_by_name: dict[str, pd.Series] | None,
    all_days: list,
    config: AgentsConfig | None = None,
    decay_result: dict | None = None,
    drift_findings: list[dict] | None = None,
) -> list[Finding]:
    config = config or AgentsConfig()
    findings: list[Finding] = []

    n_trades = alpha_result.get("n_trades", 0) or 0
    if n_trades < config.min_trades_for_sample_gate:
        findings.append(Finding(
            "LOW_SAMPLE", "MEDIUM",
            f"Only {n_trades} trades (< {config.min_trades_for_sample_gate}) — statistics are noisy "
            f"and confidence intervals wide.",
        ))

    dsr = alpha_result.get("dsr")
    if dsr is not None and dsr == dsr and dsr < config.dsr_overfit_threshold:
        findings.append(Finding(
            "OVERFIT_RISK", "HIGH",
            f"Deflated Sharpe Ratio {dsr:.2f} < {config.dsr_overfit_threshold} — the raw Sharpe is "
            f"plausibly a multiple-testing artifact, not genuine skill.",
        ))

    pbo = pbo_result.get("pbo") if pbo_result else None
    if pbo is not None and pbo == pbo and pbo > config.pbo_overfit_threshold:
        findings.append(Finding(
            "OVERFIT_RISK", "MEDIUM",
            f"Pool-level Probability of Backtest Overfitting {pbo:.1%} > "
            f"{config.pbo_overfit_threshold:.0%} — the selection process across the trial pool "
            f"shows overfitting risk, independent of this specific alpha.",
        ))

    if conditional_ev_table is not None and not conditional_ev_table.empty:
        total = len(conditional_ev_table)
        negative = int((conditional_ev_table["ev_dollars"] < 0).sum())
        if total and (negative / total) > config.regime_fragile_negative_fraction:
            findings.append(Finding(
                "REGIME_FRAGILE", "MEDIUM",
                f"{negative}/{total} regimes show negative EV/trade — the edge may be a regime-specific "
                f"accident rather than a general mechanism.",
            ))

    breakeven = alpha_result.get("breakeven_cost_profile")
    if breakeven is None:
        findings.append(Finding("EXECUTION_SENSITIVE", "HIGH",
                                 "Unprofitable even at optimistic costs — the edge may be a cost-model artifact."))
    elif breakeven == "optimistic":
        findings.append(Finding("EXECUTION_SENSITIVE", "MEDIUM",
                                 "Only survives the optimistic cost profile — thin margin of safety against real slippage."))

    if alpha_daily_pnl is not None and baseline_daily_pnl_by_name:
        matrix = build_pnl_matrix({"__alpha__": alpha_daily_pnl, **baseline_daily_pnl_by_name}, all_days)
        if len(matrix) > 10:
            corr_matrix = matrix.corr()
            for name in baseline_daily_pnl_by_name:
                corr = corr_matrix.loc["__alpha__", name]
                if corr == corr and abs(corr) > config.baseline_correlation_threshold:
                    findings.append(Finding(
                        "HIDDEN_CORRELATION", "HIGH",
                        f"Daily P&L correlation {corr:.2f} with the trivial baseline '{name}' — this "
                        f"alpha may just be rediscovering it, not an independent edge.",
                    ))

    if decay_result is not None:
        level = decay_result.get("level")
        reason = decay_result.get("reason", "")
        if level == "RED":
            findings.append(Finding("ALPHA_DECAY", "HIGH", f"Shadow-mode decay level RED — {reason}"))
        elif level == "ORANGE":
            findings.append(Finding("ALPHA_DECAY", "MEDIUM", f"Shadow-mode decay level ORANGE — {reason}"))
        elif level == "YELLOW":
            findings.append(Finding("ALPHA_DECAY", "LOW", f"Shadow-mode decay level YELLOW — {reason}"))

    if drift_findings:
        drifted = [f for f in drift_findings if f.get("drifted")]
        if drifted:
            detail = ", ".join(f"{f['feature']} (PSI={f['psi']:.2f})" for f in drifted)
            findings.append(Finding(
                "FEATURE_DRIFT", "MEDIUM",
                f"{len(drifted)}/{len(drift_findings)} monitored features show PSI above the "
                f"configured drift threshold between the in-sample and shadow periods: {detail}.",
            ))

    return findings
