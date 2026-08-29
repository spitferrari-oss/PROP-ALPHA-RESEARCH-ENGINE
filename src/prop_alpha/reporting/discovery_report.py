"""Discovery run report (spec §18/§19/§48): the combinatorial-search
survivors and the symbolic-regression scan, plus a pointer to the
Hypothesis Ledger every candidate (survivor or not) was logged to.
"""
from __future__ import annotations

from pathlib import Path


def generate_discovery_report(
    discovery_result: dict,
    experiment_id: str,
    meta: dict,
    top_n: int = 15,
    out_dir: str | Path = "reports",
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# PROP ALPHA RESEARCH ENGINE — Discovery Report",
        "",
        f"**Experiment ID:** {experiment_id}  ",
        f"**Git commit:** {meta.get('git_commit', 'unknown')}  ",
        f"**Config hash:** {meta.get('config_hash', 'unknown')}  ",
        f"**Dataset hash:** {meta.get('dataset_hash', 'unknown')}  ",
        f"**Dataset source:** {meta.get('dataset_source', 'unknown')} "
        f"(SYNTHETIC data must never be treated as real market evidence)  ",
        f"**Seed:** {meta.get('seed', 'unknown')}  ",
        "",
        f"Generated {discovery_result['n_candidates']} candidate setups via combinatorial search "
        f"(spec §18/§19 Level 2); {discovery_result['n_passed_screen']} passed the quick IS/OOS "
        f"screen. **Every candidate — survivor or not — was logged to the Hypothesis Ledger** at "
        f"`{discovery_result['ledger_path']}` (spec §20).",
        "",
        "Passing the quick screen means `HYPOTHESIS` -> `BACKTESTED` only: enough trades, and "
        "positive EV/day on both the in-sample and out-of-sample slices. None of this is the full "
        "Phase 4 statistical validation (walk-forward, bootstrap, PBO/DSR, cost sensitivity) — a "
        "promising survivor should be hand-coded as a `Strategy` and added to `cli.ALPHA_STRATEGIES` "
        "to go through `pae research full-run`'s full gates before it means anything.",
        "",
        "## Combinatorial Search Survivors",
        "",
    ]

    survivors = discovery_result["survivors"][:top_n]
    if survivors:
        lines += [
            "| Rank | Alpha | Mechanism | Trades | Win Rate | IS EV/day ($) | OOS EV/day ($) |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for i, r in enumerate(survivors, start=1):
            lines.append(
                f"| {i} | {r['alpha_name']} | {r['mechanism']} | {r['n_trades']} | "
                f"{r['win_rate']:.1%} | {r['is_ev_per_day']:.2f} | {r['oos_ev_per_day']:.2f} |"
            )
    else:
        lines.append(
            "No candidate passed the quick screen on this dataset/seed — see the Hypothesis "
            "Ledger for the full set of attempted (and retired) candidates."
        )
    lines.append("")

    lines += [
        "## Symbolic Regression — Simple Expressions vs. Forward Return (spec §48)",
        "",
        "Ranked by |Spearman IC| against a short-horizon forward return, ties broken toward "
        "fewer terms (spec §49: prefer the simpler formula at equal performance). This is a "
        "raw-signal scan, not a tradeable setup — it points at *which features* carry "
        "information, for a human to turn into a hypothesis.",
        "",
        "| Rank | Expression | IC | Complexity | N obs |",
        "|---|---|---:|---:|---:|",
    ]
    for i, r in enumerate(discovery_result["symbolic_results"], start=1):
        lines.append(f"| {i} | `{r['expression']}` | {r['ic']:.3f} | {r['complexity']} | {r['n_obs']} |")
    lines.append("")

    report_path = out_dir / f"{experiment_id}_discovery_report.md"
    report_path.write_text("\n".join(lines))
    return report_path
