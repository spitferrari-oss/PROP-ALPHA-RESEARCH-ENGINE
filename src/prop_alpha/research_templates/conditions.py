"""GEX/DEX-aware condition library (extension §111-114), built on the
exact same `discovery.conditions.Condition` shape the core Discovery
Engine uses — a named boolean predicate over already-computed columns, so
composing a GEX condition with a futures condition (`templates.py`) never
introduces look-ahead beyond what `research_templates.gex_market_frame.
enrich_synced_frame_with_gex_features` already guarantees.

Every condition here is a *state* label, never a directional claim
(extension §37's No-Assumption Principle) — "GEX regime is currently
POSITIVE_GAMMA" is not "price will therefore do X." `dex_sign` is used
instead of a raw DEX magnitude threshold because DEX has no established
normalization the way GEX does (`options.features.normalize_gex_series`);
an arbitrary magnitude cutoff would be exactly the "scale-dependent
absolute threshold" extension §67 warns against, so magnitude is
deliberately left out of this library until it has one.
"""
from __future__ import annotations

from prop_alpha.discovery.conditions import Condition
from prop_alpha.options.features import GexRegime

_POSITIVE_REGIMES = (GexRegime.POSITIVE_GAMMA.value, GexRegime.STRONG_POSITIVE_GAMMA.value)
_NEGATIVE_REGIMES = (GexRegime.NEGATIVE_GAMMA.value, GexRegime.STRONG_NEGATIVE_GAMMA.value)

GEX_CONDITION_LIBRARY: list[Condition] = [
    Condition("gex_regime_strong_positive", lambda df: df["gex_regime"] == GexRegime.STRONG_POSITIVE_GAMMA.value,
              "GEX regime classified strongly positive (z-scored, extension §31)"),
    Condition("gex_regime_positive", lambda df: df["gex_regime"].isin(_POSITIVE_REGIMES),
              "GEX regime classified positive (including strongly positive)"),
    Condition("gex_regime_negative", lambda df: df["gex_regime"].isin(_NEGATIVE_REGIMES),
              "GEX regime classified negative (including strongly negative)"),
    Condition("gex_regime_strong_negative", lambda df: df["gex_regime"] == GexRegime.STRONG_NEGATIVE_GAMMA.value,
              "GEX regime classified strongly negative (z-scored, extension §31)"),
    Condition("gex_regime_neutral", lambda df: df["gex_regime"] == GexRegime.NEUTRAL.value,
              "GEX regime classified neutral"),
    Condition("dex_sign_positive", lambda df: df["dex_sign"] == 1.0,
              "net dealer delta exposure currently positive (extension §32)"),
    Condition("dex_sign_negative", lambda df: df["dex_sign"] == -1.0,
              "net dealer delta exposure currently negative (extension §32)"),
    Condition("above_gamma_flip", lambda df: df["close"] > df["options_gamma_flip"],
              "price trading above the reported gamma flip level"),
    Condition("below_gamma_flip", lambda df: df["close"] < df["options_gamma_flip"],
              "price trading below the reported gamma flip level"),
    Condition("near_gamma_flip", lambda df: (df["close"] - df["options_gamma_flip"]).abs() < df["atr_14"],
              "price within one ATR of the reported gamma flip level"),
    Condition("above_major_positive_gamma", lambda df: df["close"] > df["options_major_positive_gamma"],
              "price trading above the reported major positive gamma level"),
    Condition("below_major_negative_gamma", lambda df: df["close"] < df["options_major_negative_gamma"],
              "price trading below the reported major negative gamma level"),
]
