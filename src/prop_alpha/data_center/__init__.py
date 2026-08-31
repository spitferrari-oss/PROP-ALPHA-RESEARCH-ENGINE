"""Data Center dashboard (extension spec §21/§54/§105-109, Phase M).

Aggregates the health/status objects earlier phases already compute —
`data.live.health.FeedHealth` (futures feed, §19-21), `options.gexbot.
health.GexbotHealth` (options feed, §90), `data.quality_engine.
DataQualityReport` (§19-20/§54), and `market_state.vector.MarketState`'s
`completeness` (§44) — into one cross-market status snapshot and renders
it as a markdown report, the same "one source of truth, not tracked
twice" discipline `FeedHealth`'s own docstring already commits to.

This module never computes health itself — it only combines what a
caller already has. Any input a caller doesn't have (no active live
connection, no quality report run yet) is passed as `None` and shows up
in the rendered report as "not available," never as a fabricated healthy
default.
"""
