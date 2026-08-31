"""Real-time trading eligibility (hardening pass Blocker E / Step 5).

Distinct from `risk.stop_trading.StopTradingPolicy`, which is a
**backtest trade filter** — it decides, after the fact, which historical
trades a hypothetical policy would have skipped, purely for comparing
policies' effect on Payout (spec §39). `trading.no_trade` is a **real-time
eligibility gate**: given the current state of the world right now,
should a trade be proposed at all. The two are complementary, not
duplicates — a live/shadow session (`live_shadow.session`) uses `no_trade`
per decision; a completed backtest's trade stream can additionally be
re-filtered through a `StopTradingPolicy` to study a day-level stop rule.
"""
