"""Cross-market Market State vector (extension spec §43-44, Phase L).

Two pieces:

- `location`: the Location Engine (§43) — `MarketLocation`, the distance
  from the current price to every relevant futures/options level (VWAP,
  volume profile, prior-day range, opening range, gamma levels, ...).
- `vector`: the Market State vector itself (§44) — `MarketState`, the
  10-component snapshot (price/volume/volatility/liquidity/orderflow/
  profile/session/regime/options/event state) that downstream research
  (Phase P) will condition on.

Neither component fabricates data it doesn't have: a futures bar missing a
feature column, an absent options snapshot, or the (currently nonexistent)
Event Engine's state all leave the corresponding slot empty rather than
defaulted.
"""
