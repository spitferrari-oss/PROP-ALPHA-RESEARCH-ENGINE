"""Databento adapter (extension spec §3-4, primary futures data provider).

Empty on purpose: `historical.py` (implementing `FuturesDataProvider.get_historical`
+ `get_instrument_definition`/`get_trading_calendar` via `symbology.py`) is
Phase B; `live.py` (`subscribe_live`) is Phase C — see §152's implementation
order. Building either now, before the interface they implement (see
`providers.base`) has a real consumer, would be exactly the "codice inutile"
§3 warns against.
"""
