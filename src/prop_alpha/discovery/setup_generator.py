"""Setup Generator / Combinatorial Search (spec §18, §19 Level 2).

Programmatically composes candidate setups from the condition library
(single conditions and pairs, both directions) rather than hand-coding
each one — "il sistema deve poter generare migliaia di combinazioni ma
NON deve considerarle automaticamente valide" (§18): generation here is
deliberately decoupled from validation, which happens in `screening.py`
and, for anything promoted further, the existing Phase 4-6 gates.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from prop_alpha.discovery.conditions import Condition
from prop_alpha.strategies.base import AlphaMeta, Strategy


class GeneratedStrategy(Strategy):
    """A candidate setup: AND of 1-2 conditions from the library, fixed
    direction, entry trigger = all conditions true. Exit logic (stop/target)
    reuses the same ATR-based risk model every hand-coded alpha uses
    (`Strategy.with_risk_levels`), so a discovered candidate is directly
    comparable to the 12 baseline alphas.
    """

    def __init__(self, alpha_id: str, conditions: list[Condition], direction: int):
        if direction not in (1, -1):
            raise ValueError("direction must be 1 (long) or -1 (short)")
        self.conditions = conditions
        self.direction = direction
        cond_names = " & ".join(c.name for c in conditions)
        regimes = sorted({c.regime_hint for c in conditions if c.regime_hint})
        self.meta = AlphaMeta(
            alpha_id=alpha_id,
            alpha_name=f"{'LONG' if direction == 1 else 'SHORT'}: {cond_names}",
            family="DISCOVERED",
            subcategory="combinatorial search",
            directionality="LONG" if direction == 1 else "SHORT",
            mechanism="; ".join(c.mechanism_hint for c in conditions),
            research_status="HYPOTHESIS",
        )
        self._regimes = regimes

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        mask = pd.Series(True, index=df.index)
        for condition in self.conditions:
            mask &= condition.fn(df).fillna(False)
        df["direction"] = np.where(mask, self.direction, 0)
        return df


def generate_candidate_setups(
    library: list[Condition],
    max_combo_size: int = 2,
    max_candidates: int = 150,
    seed: int = 42,
) -> list[GeneratedStrategy]:
    if max_combo_size not in (1, 2):
        raise ValueError("max_combo_size must be 1 or 2 (larger combos overfit fast on a small condition pool)")

    candidates: list[GeneratedStrategy] = []
    counter = 1

    for condition in library:
        for direction in (1, -1):
            if len(candidates) >= max_candidates:
                return candidates
            candidates.append(GeneratedStrategy(f"DISC_{counter:04d}", [condition], direction))
            counter += 1

    if max_combo_size == 2:
        pairs = list(itertools.combinations(library, 2))
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(pairs))
        for idx in order:
            c1, c2 = pairs[idx]
            for direction in (1, -1):
                if len(candidates) >= max_candidates:
                    return candidates
                candidates.append(GeneratedStrategy(f"DISC_{counter:04d}", [c1, c2], direction))
                counter += 1

    return candidates
