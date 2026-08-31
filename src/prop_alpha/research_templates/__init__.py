"""GEX/Futures Research Experiment Templates (extension spec §111-114,
Phase P) — the last of the extension's own numbered phases.

This does not duplicate the core Discovery Engine (Phase 7, `discovery/`):
it extends the exact same machinery (`discovery.conditions.Condition`,
`discovery.setup_generator.GeneratedStrategy`, `discovery.screening.
quick_evaluate`, `discovery.hypothesis.Hypothesis`/`HypothesisLedger`)
with an options/GEX-aware condition library and a cross-market template
generator that explicitly pairs one futures condition with one GEX
condition per candidate — a "GEX/futures template" — rather than mixing
everything into one flat combinatorial pool the way the core engine's
`generate_candidate_setups` does for futures-only conditions.

No-Assumption Principle (extension §37, still binding here): every GEX
condition is a state label only ("GEX regime is currently X", "price is
above the gamma flip") — never a directional claim about what that state
implies for price. Whether any of these auto-generated templates actually
predict anything is exactly what `quick_evaluate`/the Hypothesis Ledger/
the full Phase 4-6 gates exist to test, empirically, same as any other
discovered candidate.
"""
