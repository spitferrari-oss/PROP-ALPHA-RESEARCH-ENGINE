"""Provider abstraction (Data Feed + Options Intelligence extension, §1-3).

The PARE core (features/regimes/strategies/backtest/risk) must never import
a vendor SDK directly. Every external data source implements one of the
two interfaces in `providers.base` — `FuturesDataProvider` or
`OptionsDataProvider` — and concrete adapters live in their own
vendor-named subpackage (`providers.databento`, `providers.gexbot`, ...),
added one at a time as later extension phases build them out (§152 Phase
B/C for Databento, Phase H for GEXBOT). Nothing here depends on network
access or a specific vendor's client library.
"""
