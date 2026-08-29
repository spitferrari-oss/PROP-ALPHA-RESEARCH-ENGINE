"""Research report generation (spec §65 Backtest Report, §113 Top Alpha
Report). Ranking follows spec §134: Expected Payout first, then P(Breach)
(lower is better), then EV/day.

Baseline comparators (spec §90: Buy & Hold, Random Entry, Random Direction,
Simple MA, Simple Breakout, Simple Mean Reversion — tagged family=BASELINE)
are reported separately from the ranked alpha table, since the point of a
baseline is to show what an alpha must beat, not to compete for rank.

Phase 4 adds cross-strategy overfitting diagnostics (PBO, DSR — spec §30)
and per-alpha walk-forward/cost-sensitivity results (spec §26, §23/§24).
"""
from __future__ import annotations

from pathlib import Path

from prop_alpha.risk.payout_optimizer import rank_policies_by_expected_payout

TABLE_HEADER = (
    "| Rank | Alpha | Family | Trades | EV/trade ($) | EV/day ($) | "
    "Win Rate | Max DD ($) | P(Breach) | P(Payout) | Expected Payout ($) | DSR | Status |"
)
TABLE_SEP = "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"


def rank_alphas(results: list[dict]) -> list[dict]:
    return sorted(
        results,
        key=lambda r: (-r["expected_payout"], r["p_breach"], -r["ev_per_day_dollars"]),
    )


def _fmt_pct(x) -> str:
    return "n/a" if x is None or x != x else f"{x:.1%}"


def _table_row(i: int, r: dict) -> str:
    dsr = r.get("dsr", float("nan"))
    dsr_str = "n/a" if dsr != dsr else f"{dsr:.2f}"
    return (
        f"| {i} | {r['alpha_name']} | {r['family']} | {r['n_trades']} | "
        f"{r['ev_per_trade_dollars']:.2f} | {r['ev_per_day_dollars']:.2f} | "
        f"{r['win_rate']:.1%} | {r['max_drawdown']:.0f} | {r['p_breach']:.1%} | "
        f"{r['p_payout']:.1%} | {r['expected_payout']:.0f} | {dsr_str} | {r['research_status']} |"
    )


def _detail_block(r: dict) -> list[str]:
    lines = [
        f"### {r['alpha_name']} ({r['alpha_id']})",
        "",
        f"- Family: {r['family']} | Mechanism: {r.get('mechanism', 'n/a')}",
        f"- Trades: {r['n_trades']} | Trades/day: {r.get('trades_per_day', float('nan')):.2f}",
        f"- Win rate: {r['win_rate']:.1%} | Profit factor: {r.get('profit_factor', float('nan')):.2f}",
        f"- Expectancy: {r.get('expectancy_r', float('nan')):.3f}R "
        f"(avg winner {r.get('avg_winner_r', float('nan')):.2f}R / "
        f"avg loser {r.get('avg_loser_r', float('nan')):.2f}R)",
        f"- EV/day: ${r['ev_per_day_dollars']:.2f} | Std daily P&L: "
        f"${r.get('std_daily_pnl', float('nan')):.2f} | Sharpe (daily, annualized): "
        f"{r.get('sharpe_daily', float('nan')):.2f}",
        f"- Max drawdown (trade sequence): ${r['max_drawdown']:.0f}",
        f"- Bootstrap EV/day 90% CI: [{r.get('boot_ev_p5', float('nan')):.2f}, "
        f"{r.get('boot_ev_p95', float('nan')):.2f}]",
        f"- Monte Carlo ({r.get('mc_n_paths', 'n/a')} paths, "
        f"{r.get('mc_n_days', 'n/a')}-day horizon): P(Breach)={r['p_breach']:.1%}, "
        f"P(Payout)={r['p_payout']:.1%}, Expected days to payout="
        f"{r.get('expected_days_to_payout', float('nan')):.1f}",
        f"- Deflated Sharpe Ratio: {_fmt_pct(r.get('dsr'))} "
        "(probability the Sharpe isn't a multiple-testing artifact, spec §30)",
    ]

    if r.get("wf_n_folds"):
        fold_evs = ", ".join(
            f"${v:.0f}" if v == v else "n/a"
            for v in (r.get("wf_fold_ev_per_day") or [])
        )
        lines.append(
            f"- Walk-forward ({r['wf_n_folds']} sequential folds): "
            f"{_fmt_pct(r.get('wf_positive_fold_fraction'))} of folds EV/day-positive, "
            f"worst fold EV/day ${r.get('wf_worst_fold_ev_per_day', float('nan')):.2f}"
            + (f" [{fold_evs}]" if fold_evs else "")
        )

    cost_sens = r.get("cost_sensitivity")
    if cost_sens:
        curve = ", ".join(f"{k}=${v:.0f}" for k, v in cost_sens.items() if v == v)
        lines.append(
            f"- Cost sensitivity (EV/day by profile): {curve} | "
            f"breakeven cost profile: {r.get('breakeven_cost_profile') or 'none (unprofitable even optimistic)'}"
        )

    lines += [f"- Research status: {r['research_status']}", ""]
    return lines


def _diagnostics_section(diagnostics: dict | None) -> list[str]:
    if not diagnostics:
        return []
    pbo = diagnostics.get("pbo") or {}
    lines = [
        "## Statistical Validation — Overfitting Control (spec §30)",
        "",
        "Computed once across the alpha trial pool (not per-strategy): PBO asks how "
        "often the best in-sample strategy would have ranked below the out-of-sample "
        "median; a low DSR means a strategy's Sharpe is plausibly a multiple-testing "
        "artifact even if it looks good raw.",
        "",
        f"**Probability of Backtest Overfitting (CSCV):** {_fmt_pct(pbo.get('pbo'))} "
        f"({pbo.get('n_combinations', 0)} combinations, {pbo.get('n_strategies', 0)} "
        f"strategies, {pbo.get('n_splits', 0)} blocks)",
        "",
    ]

    policy_results = diagnostics.get("payout_optimizer")
    alpha_name = diagnostics.get("payout_optimizer_alpha_name")
    if policy_results:
        lines += [
            f"## Payout Optimizer — Risk & Stop-Trading Policies for {alpha_name} (spec §38)",
            "",
            "Same trade sequence, five sizing/stop-trading policies (spec §38's own worked "
            "examples) — ranked by Expected Payout, not raw EV/day, since a policy that "
            "survives prop constraints more often can out-earn one with higher unconstrained EV.",
            "",
            "| Rank | Policy | Rule | Trades | Avg Contracts | EV/day ($) | Max DD ($) | "
            "P(Breach) | P(Payout) | Expected Payout ($) |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        ranked_policies = rank_policies_by_expected_payout(policy_results)
        for i, p in enumerate(ranked_policies, start=1):
            lines.append(
                f"| {i} | {p['policy_name']} | {p['description']} | {p['n_trades']} | "
                f"{p['avg_contracts']:.1f} | {p['ev_per_day_dollars']:.2f} | {p['max_drawdown']:.0f} | "
                f"{p['p_breach']:.1%} | {p['p_payout']:.1%} | {p['expected_payout']:.0f} |"
            )
        lines.append("")
        if all(p["n_trades"] == 0 for p in policy_results):
            lines += [
                "All policies sized 0 contracts for every trade: the fixed-risk budget "
                "(`risk.risk_per_trade` x `prop.account_size`) can't afford even 1 contract at this "
                "alpha's stop distances given `market.point_value`. This is the Position Sizing "
                "Engine correctly refusing to size (spec §37), not a strategy failure — raise "
                "`risk.risk_per_trade`, `prop.account_size`, or trade a smaller-point-value "
                "instrument (e.g. MNQ instead of NQ) to see it size real positions.",
                "",
            ]

    conditional_ev_table = diagnostics.get("conditional_ev_table")
    ce_alpha_name = diagnostics.get("conditional_ev_alpha_name")
    if conditional_ev_table is not None and not conditional_ev_table.empty:
        lines += [
            f"## Conditional Expected Value by Regime for {ce_alpha_name} (spec §14)",
            "",
            "\"When does the idea work, not just does it work\" — the same trade sequence "
            "broken down by the rule-based regime (spec §12) active at each trade's entry bar.",
            "",
            "| Regime | Trades | Win Rate | Avg R | EV/trade ($) |",
            "|---|---:|---:|---:|---:|",
        ]
        for _, row in conditional_ev_table.iterrows():
            lines.append(
                f"| {row['regime_rule']} | {row['n_trades']} | {row['win_rate']:.1%} | "
                f"{row['avg_r']:.2f} | {row['ev_dollars']:.2f} |"
            )
        lines.append("")

    return lines


def generate_report(
    results: list[dict],
    experiment_id: str,
    meta: dict,
    diagnostics: dict | None = None,
    out_dir: str | Path = "reports",
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    alphas = [r for r in results if r["family"] != "BASELINE"]
    baselines = [r for r in results if r["family"] == "BASELINE"]
    ranked_alphas = rank_alphas(alphas)
    ranked_baselines = rank_alphas(baselines)

    lines = [
        "# PROP ALPHA RESEARCH ENGINE — Research Report",
        "",
        f"**Experiment ID:** {experiment_id}  ",
        f"**Git commit:** {meta.get('git_commit', 'unknown')}  ",
        f"**Config hash:** {meta.get('config_hash', 'unknown')}  ",
        f"**Dataset hash:** {meta.get('dataset_hash', 'unknown')}  ",
        f"**Dataset source:** {meta.get('dataset_source', 'unknown')} "
        f"(SYNTHETIC data must never be treated as real market evidence)  ",
        f"**Seed:** {meta.get('seed', 'unknown')}  ",
        "",
        "## Top Alpha Ranking",
        "",
        TABLE_HEADER,
        TABLE_SEP,
    ]
    lines += [_table_row(i, r) for i, r in enumerate(ranked_alphas, start=1)]

    if ranked_baselines:
        lines += [
            "",
            "## Baseline Comparators (spec §90 — no-edge benchmarks every alpha must beat)",
            "",
            TABLE_HEADER,
            TABLE_SEP,
        ]
        lines += [_table_row(i, r) for i, r in enumerate(ranked_baselines, start=1)]

        best_alpha = ranked_alphas[0] if ranked_alphas else None
        best_baseline = ranked_baselines[0] if ranked_baselines else None
        if best_alpha and best_baseline:
            edge = best_alpha["ev_per_day_dollars"] - best_baseline["ev_per_day_dollars"]
            lines += [
                "",
                f"Best alpha ({best_alpha['alpha_name']}) EV/day \\${best_alpha['ev_per_day_dollars']:.2f} "
                f"vs. best baseline ({best_baseline['alpha_name']}) EV/day "
                f"\\${best_baseline['ev_per_day_dollars']:.2f} — incremental EV/day: \\${edge:.2f}.",
            ]

    lines += [""] + _diagnostics_section(diagnostics)

    lines += ["## Per-Alpha Detail", ""]
    for r in ranked_alphas:
        lines += _detail_block(r)

    if ranked_baselines:
        lines += ["## Per-Baseline Detail", ""]
        for r in ranked_baselines:
            lines += _detail_block(r)

    report_path = out_dir / f"{experiment_id}_report.md"
    report_path.write_text("\n".join(lines))
    return report_path
