"""Enriches a `sync.cross_market.synchronize_frame` output with the
GEX/DEX feature columns the templates in this package's `conditions.py`
need — `options.features.classify_gex_regime_series`/`compute_dex_state`
(Phase K) applied over `synchronize_frame`'s `options_gex`/`options_dex`
columns, which are otherwise raw metric values with no state
classification attached.

A futures bar with no options snapshot within sync tolerance already has
`NaN` in every `options_*` column (`sync.cross_market.synchronize_frame`'s
own contract) — `classify_gex_regime_series`/`compute_dex_state` both
already handle `NaN` input honestly (an `UNKNOWN` GEX regime, `NaN`
DEX state), so no extra handling is needed here.
"""
from __future__ import annotations

import pandas as pd

from prop_alpha.options.features import classify_gex_regime_series, compute_dex_state

_REQUIRED_COLUMNS = ("options_gex", "options_dex")


def enrich_synced_frame_with_gex_features(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"enrich_synced_frame_with_gex_features: missing required column(s) {missing} — "
            f"pass the output of sync.cross_market.synchronize_frame."
        )

    result = df.copy()
    result["gex_regime"] = classify_gex_regime_series(df["options_gex"])
    result = pd.concat([result, compute_dex_state(df["options_dex"])], axis=1)
    return result
