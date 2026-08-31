"""Parameter sensitivity analysis (hardening pass Step 48).

Distinct from `statistics.cost_sensitivity` (which stresses commission/
slippage *cost* assumptions around a fixed strategy) and from the
Discovery Engine's combinatorial search (which searches over which
*conditions* to combine, not a single strategy's own numeric
parameters). This module perturbs a strategy's own numeric parameters
(e.g. `stop_atr_mult`, `target_r_multiple`) around a chosen base point
and reports how sensitive a metric (typically OOS EV/day) is to small
changes — a strategy whose EV collapses or flips sign from a 10% nudge
in one parameter is more likely curve-fit to the exact base value than
genuinely robust, independent of whatever the core statistical gates
(walk-forward, PBO, DSR) already say about the base point alone.

The caller supplies `evaluate`, a function from `{param_name: value}` to
a scalar metric (or `None` if that combination couldn't be evaluated,
e.g. zero trades) — this module has no opinion on what strategy/backtest
machinery produces that metric, so it works for any of this repo's
existing `GeneratedStrategy`/hand-coded `Strategy` objects without
depending on either.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

EvaluateFn = Callable[[dict], "float | None"]


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    base_value: float
    perturbation_pct: float = 0.1
    grid_values: tuple[float, ...] | None = None

    def points(self) -> list[float]:
        if self.grid_values is not None:
            return list(self.grid_values)
        delta = abs(self.base_value) * self.perturbation_pct
        if delta == 0:
            return [self.base_value]
        return [self.base_value - delta, self.base_value, self.base_value + delta]


@dataclass(frozen=True)
class ParameterPointResult:
    params: dict
    metric_value: float | None


@dataclass(frozen=True)
class ParameterSensitivityResult:
    base_params: dict
    base_metric_value: float | None
    points: tuple[ParameterPointResult, ...] = field(default_factory=tuple)
    stability_score: float | None = None
    best_point: ParameterPointResult | None = None
    worst_point: ParameterPointResult | None = None

    def evaluated_points(self) -> list[ParameterPointResult]:
        return [p for p in self.points if p.metric_value is not None]


def _stability_score(
    evaluated: list[ParameterPointResult], base_value: float | None, tolerance_fraction: float = 0.5,
) -> float | None:
    """Fraction of the evaluated neighborhood whose metric keeps the same
    sign as the base value and stays within `tolerance_fraction` of the
    base's magnitude — `1.0` means the whole neighborhood agrees with the
    base point, `0.0` means every neighbor disagrees. `None` when there's
    no base value (or it's zero) to compare against, rather than a
    fabricated score.
    """
    if not evaluated or base_value is None or base_value == 0:
        return None
    values = np.array([p.metric_value for p in evaluated], dtype=float)
    same_sign = values * base_value > 0
    within_tolerance = np.abs(values - base_value) <= tolerance_fraction * abs(base_value)
    return float(np.mean(same_sign & within_tolerance))


def grid_sensitivity(
    specs: list[ParameterSpec],
    evaluate: EvaluateFn,
    tolerance_fraction: float = 0.5,
) -> ParameterSensitivityResult:
    """Cartesian product over every spec's points — for one `ParameterSpec`
    this is exactly local perturbation (base value +/- `perturbation_pct`);
    for several it's a genuine grid over their joint neighborhood.
    """
    if not specs:
        raise ValueError("grid_sensitivity requires at least one ParameterSpec.")

    base_params = {s.name: s.base_value for s in specs}
    base_metric_value = evaluate(base_params)

    names = [s.name for s in specs]
    grids = [s.points() for s in specs]

    points = [
        ParameterPointResult(params=dict(zip(names, combo)), metric_value=evaluate(dict(zip(names, combo))))
        for combo in itertools.product(*grids)
    ]

    evaluated = [p for p in points if p.metric_value is not None]
    stability = _stability_score(evaluated, base_metric_value, tolerance_fraction)
    best_point = max(evaluated, key=lambda p: p.metric_value) if evaluated else None
    worst_point = min(evaluated, key=lambda p: p.metric_value) if evaluated else None

    return ParameterSensitivityResult(
        base_params=base_params, base_metric_value=base_metric_value, points=tuple(points),
        stability_score=stability, best_point=best_point, worst_point=worst_point,
    )


def local_perturbation(
    spec: ParameterSpec, evaluate: EvaluateFn, tolerance_fraction: float = 0.5,
) -> ParameterSensitivityResult:
    """Convenience wrapper: local perturbation of a single parameter is
    exactly `grid_sensitivity` with a one-element spec list.
    """
    return grid_sensitivity([spec], evaluate, tolerance_fraction)
