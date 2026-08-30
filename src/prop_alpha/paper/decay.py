"""Alpha Decay Monitor (spec §97/§98): classifies shadow-period performance
against the in-sample bootstrap CI already computed in Phase 4, using the
four mechanically-checkable levels from spec §98:

- GREEN: shadow EV/day is within the expected (in-sample bootstrap) range.
- YELLOW: shadow EV/day has degraded more than ~1 sigma below the IS EV/day.
- ORANGE: the shadow period's own bootstrap CI for EV/day overlaps zero.
- RED: the shadow period's own bootstrap CI for EV/day is entirely negative.

spec §98 also defines a fifth level, RETIRED ("economic thesis invalidated
/ not automatable") — that is a judgment call about *why* an edge decayed,
not a statistic this module can compute, so it is never auto-assigned here
(spec §128: the system must not treat human judgment calls as automatable).
A RED classification is the signal a human should look at that question.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.backtest.metrics import daily_pnl
from prop_alpha.statistics.bootstrap import bootstrap_daily_pnl

DECAY_LEVELS = ("GREEN", "YELLOW", "ORANGE", "RED")

# p5-p95 spans ~3.29 standard deviations for a normal distribution; used as
# a rough sigma estimate from the already-computed 90% bootstrap CI rather
# than re-deriving a fresh standard error.
_P5_P95_SPAN_IN_SIGMA = 3.29


def classify_alpha_decay(
    shadow_log: pd.DataFrame,
    is_ev_per_day: float,
    is_boot_ev_p5: float,
    is_boot_ev_p95: float,
    seed: int = 42,
    n_boot: int = 1000,
    min_days_for_ci: int = 5,
) -> dict:
    daily = daily_pnl(shadow_log) if not shadow_log.empty else pd.Series(dtype=float)
    n_days = len(daily)

    if n_days == 0:
        return {
            "level": "GREEN",
            "reason": "No shadow trades yet — nothing to degrade from.",
            "n_shadow_days": 0,
            "shadow_ev_per_day": float("nan"),
            "shadow_boot_ci": None,
        }

    shadow_ev = float(daily.mean())
    shadow_boot = bootstrap_daily_pnl(daily, n_boot=n_boot, seed=seed) if n_days >= min_days_for_ci else None
    ci_p5 = shadow_boot["ev_per_day"]["p5"] if shadow_boot else float("nan")
    ci_p95 = shadow_boot["ev_per_day"]["p95"] if shadow_boot else float("nan")

    persistent_negative = shadow_boot is not None and ci_p95 == ci_p95 and ci_p95 < 0
    ci_overlaps_zero = shadow_boot is not None and ci_p5 == ci_p5 and ci_p5 < 0 <= ci_p95

    is_sigma = (
        (is_boot_ev_p95 - is_boot_ev_p5) / _P5_P95_SPAN_IN_SIGMA
        if is_boot_ev_p95 == is_boot_ev_p95 and is_boot_ev_p5 == is_boot_ev_p5
        else float("nan")
    )
    degraded_over_1sigma = (
        is_sigma == is_sigma and is_sigma > 0
        and is_ev_per_day == is_ev_per_day
        and (is_ev_per_day - shadow_ev) > is_sigma
    )

    if persistent_negative:
        level = "RED"
        reason = f"Shadow EV/day 90% CI [{ci_p5:.2f}, {ci_p95:.2f}] is entirely negative over {n_days} shadow days."
    elif ci_overlaps_zero:
        level = "ORANGE"
        reason = f"Shadow EV/day 90% CI [{ci_p5:.2f}, {ci_p95:.2f}] overlaps zero over {n_days} shadow days."
    elif degraded_over_1sigma:
        level = "YELLOW"
        reason = (
            f"Shadow EV/day ${shadow_ev:.2f} is more than one IS-bootstrap sigma "
            f"(~${is_sigma:.2f}) below IS EV/day ${is_ev_per_day:.2f}."
        )
    else:
        level = "GREEN"
        reason = f"Shadow EV/day ${shadow_ev:.2f} is within the expected range of IS EV/day ${is_ev_per_day:.2f}."

    return {
        "level": level,
        "reason": reason,
        "n_shadow_days": n_days,
        "shadow_ev_per_day": shadow_ev,
        "shadow_boot_ci": {"p5": ci_p5, "p95": ci_p95} if shadow_boot else None,
    }
