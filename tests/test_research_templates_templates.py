from prop_alpha.discovery.conditions import Condition
from prop_alpha.research_templates.templates import generate_gex_futures_templates

_FUTURES = [
    Condition("f1", lambda df: df["close"] > 0, "futures cond 1"),
    Condition("f2", lambda df: df["close"] > 0, "futures cond 2"),
]
_GEX = [
    Condition("g1", lambda df: df["close"] > 0, "gex cond 1"),
    Condition("g2", lambda df: df["close"] > 0, "gex cond 2"),
]


def test_generate_produces_one_futures_and_one_gex_condition_per_candidate():
    candidates = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=100, seed=1)
    for candidate in candidates:
        names = {c.name for c in candidate.conditions}
        assert len(candidate.conditions) == 2
        assert names & {"f1", "f2"}
        assert names & {"g1", "g2"}


def test_generate_covers_both_directions_and_full_cross_product():
    candidates = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=100, seed=1)
    # 2 futures x 2 gex = 4 pairs, x 2 directions = 8 candidates
    assert len(candidates) == 8
    directions = {c.direction for c in candidates}
    assert directions == {1, -1}


def test_generate_respects_max_candidates_cap():
    candidates = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=3, seed=1)
    assert len(candidates) == 3


def test_generate_alpha_ids_are_prefixed_and_unique():
    candidates = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=100, seed=1)
    ids = [c.meta.alpha_id for c in candidates]
    assert all(i.startswith("GEXFUT_") for i in ids)
    assert len(ids) == len(set(ids))


def test_generate_is_deterministic_for_a_fixed_seed():
    a = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=100, seed=7)
    b = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=100, seed=7)
    assert [c.meta.alpha_name for c in a] == [c.meta.alpha_name for c in b]


def test_generate_different_seeds_can_produce_different_order():
    a = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=100, seed=1)
    b = generate_gex_futures_templates(_FUTURES, _GEX, max_candidates=100, seed=2)
    assert [c.meta.alpha_name for c in a] != [c.meta.alpha_name for c in b]


def test_generate_defaults_use_core_and_gex_condition_libraries():
    candidates = generate_gex_futures_templates(max_candidates=5, seed=1)
    assert len(candidates) == 5


def test_generate_empty_libraries_yields_no_candidates():
    assert generate_gex_futures_templates([], [], max_candidates=10, seed=1) == []
