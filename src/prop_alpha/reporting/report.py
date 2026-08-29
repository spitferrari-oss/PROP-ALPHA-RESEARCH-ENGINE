"""Research report generation (spec §65 Backtest Report, §113 Top Alpha
Report). Ranking follows spec §134: Expected Payout first, then P(Breach)
(lower is better), then EV/day.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def rank_alphas(results: list[dict]) -> list[dict]:
    return sorted(
        results,
        key=lambda r: (-r["expected_payout"], r["p_breach"], -r["ev_per_day_dollars"]),
    )


def generate_report(
    results: list[dict],
    experiment_id: str,
    meta: dict,
    out_dir: str | Path = "reports",
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ranked = rank_alphas(results)

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
        "| Rank | Alpha | Family | Trades | EV/trade ($) | EV/day ($) | "
        "Win Rate | Max DD ($) | P(Breach) | P(Payout) | Expected Payout ($) | Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for i, r in enumerate(ranked, start=1):
        lines.append(
            f"| {i} | {r['alpha_name']} | {r['family']} | {r['n_trades']} | "
            f"{r['ev_per_trade_dollars']:.2f} | {r['ev_per_day_dollars']:.2f} | "
            f"{r['win_rate']:.1%} | {r['max_drawdown']:.0f} | {r['p_breach']:.1%} | "
            f"{r['p_payout']:.1%} | {r['expected_payout']:.0f} | {r['research_status']} |"
        )

    lines += ["", "## Per-Alpha Detail", ""]
    for r in ranked:
        lines += [
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
            f"- Research status: {r['research_status']}",
            "",
        ]

    report_path = out_dir / f"{experiment_id}_report.md"
    report_path.write_text("\n".join(lines))
    return report_path
