"""Market State vector (extension spec §44): `MarketState_t` — the
10-component state snapshot (price/volume/volatility/liquidity/orderflow/
profile/session/regime/options/event state) that Phase P's research
templates will condition trade outcomes on.

Deliberately one-directional: this module imports `prop_alpha.sync`,
`prop_alpha.sync` never imports this module, so there is no circular
dependency between synchronization (Phase J) and state-vector assembly
(Phase L). `sync.cross_market.CrossMarketState.market_state` (added in
Phase J) stays `None` until a caller explicitly calls `attach_market_state`
below — nothing upstream fabricates a state vector on its own.

Each of the first eight components is filled from whatever columns
`futures_bar` actually has (a research pipeline's already-computed
features); a column that isn't present, or is `None`/`NaN`, is simply
omitted from that component rather than defaulted. `event_state` is always
empty by default: no Event Engine exists anywhere in this codebase yet
(an honest, documented gap — see `docs/data_feed_extension.md`), so a
caller that has one can pass its output in, and nothing here invents it.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field, replace
from dataclasses import fields as dataclass_fields

from prop_alpha.market_state.location import MarketLocation
from prop_alpha.options.models import OptionsSnapshot
from prop_alpha.sync.cross_market import CrossMarketState

_COMPONENT_NAMES = (
    "price_state", "volume_state", "volatility_state", "liquidity_state",
    "orderflow_state", "profile_state", "session_state", "regime_state",
    "options_state", "event_state",
)

# component -> futures_bar columns it draws from (source key -> state key)
_PRICE_KEYS = ("open", "high", "low", "close", "vwap")
_VOLUME_KEYS = ("volume", "cumulative_volume", "volume_delta")
_VOLATILITY_KEYS = ("atr", "realized_vol", "implied_vol")
_LIQUIDITY_KEYS = ("bid_size", "ask_size", "spread")
_ORDERFLOW_KEYS = ("delta", "cvd", "imbalance")
_SESSION_KEYS = ("session", "minutes_since_open", "time_of_day_bucket")
_REGIME_KEYS = ("regime_rule", "regime_confidence")


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(value)
    except TypeError:
        return False


def _extract(source: dict, keys: tuple[str, ...]) -> dict:
    return {key: source[key] for key in keys if key in source and not _is_missing(source[key])}


@dataclass(frozen=True)
class MarketState:
    timestamp: dt.datetime
    price_state: dict = field(default_factory=dict)
    volume_state: dict = field(default_factory=dict)
    volatility_state: dict = field(default_factory=dict)
    liquidity_state: dict = field(default_factory=dict)
    orderflow_state: dict = field(default_factory=dict)
    profile_state: dict = field(default_factory=dict)
    session_state: dict = field(default_factory=dict)
    regime_state: dict = field(default_factory=dict)
    options_state: dict = field(default_factory=dict)
    event_state: dict = field(default_factory=dict)

    @property
    def completeness(self) -> float:
        """Fraction of the 10 components that have at least one value —
        a coarse, honest signal of how much of the vector is actually
        populated for this bar, not a claim about data quality.
        """
        non_empty = sum(1 for name in _COMPONENT_NAMES if getattr(self, name))
        return non_empty / len(_COMPONENT_NAMES)

    def as_flat_dict(self) -> dict:
        flat: dict = {}
        for name in _COMPONENT_NAMES:
            component = getattr(self, name)
            for key, value in component.items():
                flat[f"{name}.{key}"] = value
        return flat


def build_market_state(
    futures_bar: dict,
    timestamp: dt.datetime,
    market_location: MarketLocation | None = None,
    options_snapshot: OptionsSnapshot | None = None,
    event_state: dict | None = None,
) -> MarketState:
    profile_state: dict = {}
    options_state: dict = {}

    if market_location is not None:
        for distance in market_location.distances:
            key = f"distance_to_{distance.name}"
            value = distance.atr_normalized if distance.atr_normalized is not None else distance.percentage
            if distance.category == "options":
                options_state[key] = value
            else:
                profile_state[key] = value

    if options_snapshot is not None:
        for metric_field in dataclass_fields(OptionsSnapshot):
            if metric_field.name in ("timestamp", "underlying", "orderflow_state", "extra"):
                continue
            metric = getattr(options_snapshot, metric_field.name)
            if metric.value is not None:
                options_state[metric_field.name] = metric.value
            options_state[f"{metric_field.name}_status"] = metric.availability.status.value

    return MarketState(
        timestamp=timestamp,
        price_state=_extract(futures_bar, _PRICE_KEYS),
        volume_state=_extract(futures_bar, _VOLUME_KEYS),
        volatility_state=_extract(futures_bar, _VOLATILITY_KEYS),
        liquidity_state=_extract(futures_bar, _LIQUIDITY_KEYS),
        orderflow_state=_extract(futures_bar, _ORDERFLOW_KEYS),
        profile_state=profile_state,
        session_state=_extract(futures_bar, _SESSION_KEYS),
        regime_state=_extract(futures_bar, _REGIME_KEYS),
        options_state=options_state,
        event_state=dict(event_state) if event_state else {},
    )


def build_market_state_from_cross_market(
    cross_market_state: CrossMarketState,
    market_location: MarketLocation | None = None,
    event_state: dict | None = None,
) -> MarketState:
    return build_market_state(
        futures_bar=cross_market_state.futures,
        timestamp=cross_market_state.timestamp,
        market_location=market_location,
        options_snapshot=cross_market_state.options,
        event_state=event_state,
    )


def attach_market_state(
    cross_market_state: CrossMarketState,
    market_location: MarketLocation | None = None,
    event_state: dict | None = None,
) -> CrossMarketState:
    """Returns a new `CrossMarketState` with `.market_state` populated —
    never mutates `cross_market_state` (it's frozen; `dataclasses.replace`
    produces the modified copy).
    """
    market_state = build_market_state_from_cross_market(cross_market_state, market_location, event_state)
    return replace(cross_market_state, market_state=market_state.as_flat_dict())
