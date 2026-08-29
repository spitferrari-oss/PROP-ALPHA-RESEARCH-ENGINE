# Data Policy

Per spec §123–§124: **this repository does not fabricate real market data.**

## Current state: SYNTHETIC only

`prop_alpha.data.synthetic.generate_synthetic_ohlcv` produces an M15 OHLCV
series with alternating trend/range days and a synthetic buy/sell volume
split, so the feature and strategy code has something non-trivial to
compute against end-to-end. Every frame it returns carries
`df.attrs["source"] = "SYNTHETIC"`, and the research report prints this
source on every run so results can never be mistaken for evidence about a
real market.

Synthetic data here is used only for:
- unit tests
- pipeline/integration tests
- prototyping the research engine's plumbing

It must **not** be used to draw conclusions about real strategy edge. The
"Top Alpha Ranking" a `full-run` produces today is a check that the
pipeline is wired correctly and reproducible — not a trading recommendation.

## Requesting real data

When a real dataset is needed, the correct response is `DATASET_REQUIRED`
(spec §123), with:
- required schema (timestamp, open, high, low, close, volume, optionally
  buy_volume/sell_volume for order-flow features)
- frequency (currently M15 primary; see spec §6 for the full timeframe list)
- timezone (`America/New_York` is assumed by the session/VWAP logic)
- source, license, download date, coverage, granularity, adjustment
  methodology (spec §124)

No real dataset should be synthesized and presented as if it were real.

## Data layer

- Format: Parquet (`prop_alpha.data.loader.save_parquet` / `load_parquet`)
- Query: DuckDB over Parquet views (`prop_alpha.data.loader.query`)
- Directory convention (spec §77): `data/raw` → `data/features` (bronze/silver/gold
  tiers are reserved for later phases once a real ingestion pipeline exists)
