"""Cross-market template generator (extension §111-114): explicitly pairs
one futures condition with one GEX/DEX condition per candidate — a
"GEX/futures template" — reusing `discovery.setup_generator.
GeneratedStrategy` unmodified (it only needs a `list[Condition]` and a
direction; it has no idea, and doesn't need to know, that one of its two
conditions reads options-derived columns).

This is deliberately a *cross product*, not the core engine's flat
combinatorial pool (`discovery.setup_generator.generate_candidate_setups`,
which would also generate futures-only or GEX-only pairs from a merged
library) — Phase P's whole point is templates that condition a futures
setup on GEX/DEX state, so every candidate here always has exactly one of
each.
"""
from __future__ import annotations

import numpy as np

from prop_alpha.discovery.conditions import CONDITION_LIBRARY, Condition
from prop_alpha.discovery.setup_generator import GeneratedStrategy
from prop_alpha.research_templates.conditions import GEX_CONDITION_LIBRARY


def generate_gex_futures_templates(
    futures_library: list[Condition] | None = None,
    gex_library: list[Condition] | None = None,
    max_candidates: int = 150,
    seed: int = 42,
) -> list[GeneratedStrategy]:
    futures_library = futures_library if futures_library is not None else CONDITION_LIBRARY
    gex_library = gex_library if gex_library is not None else GEX_CONDITION_LIBRARY

    pairs = [
        (futures_condition, gex_condition)
        for futures_condition in futures_library
        for gex_condition in gex_library
    ]
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(pairs)) if pairs else []

    candidates: list[GeneratedStrategy] = []
    counter = 1
    for idx in order:
        futures_condition, gex_condition = pairs[idx]
        for direction in (1, -1):
            if len(candidates) >= max_candidates:
                return candidates
            candidates.append(
                GeneratedStrategy(f"GEXFUT_{counter:04d}", [futures_condition, gex_condition], direction)
            )
            counter += 1

    return candidates
