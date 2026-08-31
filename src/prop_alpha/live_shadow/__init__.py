"""Live Shadow Mode (extension spec §59/§75-80, Phase O) — the data
extension's own shadow mode, distinct from the core engine's
`paper.shadow` (spec §132, which replays an already-computed OOS trade
set). This one is wired to real market state: a `market_state.vector.
MarketState` produced from a live subscription (Phase C) or a
deterministic replay (Phase N) can generate a `TradeProposal`, which is
logged and held `PENDING` until a human reviewer explicitly approves or
rejects it via `apply_feedback`.

**This module never sends, simulates as filled, or otherwise activates a
real order** — the extension's own top-level scope statement (§132,
§162, quoted in this doc's introduction) is explicit that it stops at
data, market state, signals, and paper/shadow simulation. A `TradeProposal`
is a logged, human-reviewable record of what the system *would* have
proposed, nothing more; `feedback.apply_feedback` only ever changes a
proposal's `status` field in the append-only ledger, never executes
anything.
"""
