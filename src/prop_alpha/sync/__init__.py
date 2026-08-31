"""Futures/options synchronization (extension spec §35-36, Phase J): "Questa
è una funzione primaria" — aligning the futures and options data streams
onto a common UTC time axis within a configurable tolerance, and the
`CrossMarketState` (§36) object that pairing produces. This is the layer
Phase K's conditional-EV-by-options-state research and Phase L's full
`MarketState_t` vector both build on.
"""
