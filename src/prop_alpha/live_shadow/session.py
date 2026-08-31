"""Genuine live shadow architecture (hardening pass Step 36-39, Blocker C).

Wires the real pipeline end to end using this repo's actual components:

    PROVIDER -> NORMALIZATION -> FEATURES -> REGIME -> ALPHA ->
    NO-TRADE -> RISK -> PAPER/SHADOW PROPOSAL

`providers.base.FuturesDataProvider` (any real adapter, or `providers.
mocks.MockFuturesDataProvider`) supplies bars via `subscribe_live`;
`market_state.vector.build_market_state` (Phase L) turns each bar into a
`MarketState` (normalization/features/regime already folded into
whatever the bar dict already carries); `trading.no_trade.
evaluate_trade_eligibility` (this hardening pass) is the risk/no-trade
gate; a caller-supplied `proposal_generator` is the pluggable "alpha"
step, exactly matching `live_shadow.engine.run_live_shadow_session`'s
existing signature from Phase O — a proposal is only ever generated when
`no_trade` says eligible, and every proposal produced is logged to the
same `LiveShadowLedger` Phase O already built, never executed.

**This never sends a real order.** This module doesn't import
`execution.gateway` at all — there is no code path from here to a real
account.

Distinct from `paper.shadow` (core spec §132's OOS replay shadow, which
stays exactly as-is): that module replays an already-computed backtest
holdout; this one subscribes to an actual `FuturesDataProvider` and
builds proposals from bars as they arrive. `LiveShadowMode` makes the
distinction explicit rather than letting the two blur under one name —
`REPLAY_SHADOW` here means *this* pipeline driven by Phase N's
deterministic replay engine instead of a live subscription, which is
still not the same thing as `paper.shadow`'s OOS-holdout replay.

This environment has no background-daemon/process-supervisor
infrastructure, so "start/status/stop" are implemented honestly as a
synchronous run plus a status file on disk (`DEFAULT_STATUS_PATH`), not a
real background service — `stop_live_shadow_session` marks the on-disk
status `STOPPED` rather than pretending to signal a process that doesn't
exist in this deployment model.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from prop_alpha.data_center.status import DATA_SOURCES
from prop_alpha.live_shadow.ledger import LiveShadowLedger
from prop_alpha.live_shadow.proposal import TradeProposal
from prop_alpha.market_state.vector import MarketState, build_market_state
from prop_alpha.providers.base import FuturesDataProvider
from prop_alpha.trading.no_trade import NoTradeThresholds, TradeState, evaluate_trade_eligibility

DEFAULT_STATUS_PATH = Path("research_memory/live_shadow/session_status.json")


class LiveShadowMode(str, Enum):
    REPLAY_SHADOW = "REPLAY_SHADOW"
    LIVE_SHADOW = "LIVE_SHADOW"
    PAPER = "PAPER"
    LIVE_HUMAN_APPROVAL = "LIVE_HUMAN_APPROVAL"
    LIVE_AUTO = "LIVE_AUTO"  # never actually enabled anywhere in this repository — see execution.gateway


class SessionState(str, Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class LiveShadowSessionStatus:
    mode: str
    state: str
    data_source: str
    provider_name: str | None
    started_at: str | None
    last_event_at: str | None
    n_events: int
    n_proposals: int
    message: str = ""

    def save(self, path: str | Path = DEFAULT_STATUS_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        return path

    @classmethod
    def load(cls, path: str | Path = DEFAULT_STATUS_PATH) -> "LiveShadowSessionStatus":
        path = Path(path)
        if not path.exists():
            return cls(
                mode=LiveShadowMode.LIVE_SHADOW.value, state=SessionState.NOT_CONNECTED.value,
                data_source="NOT_CONNECTED", provider_name=None, started_at=None, last_event_at=None,
                n_events=0, n_proposals=0, message="no session has been started",
            )
        return cls(**json.loads(path.read_text()))


def _default_no_trade_state(state: MarketState) -> TradeState:
    """The default `no_trade_state_builder`: deliberately supplies no
    `alpha_ev_per_day` (this generic pipeline has no alpha wired in), so
    `evaluate_trade_eligibility`'s foundational fail-closed check
    (`NO_EDGE`) blocks every proposal by default — the honestly
    conservative starting point. A caller that wants real proposals wires
    its own `no_trade_state_builder` supplying a real EV estimate.
    """
    return TradeState(
        alpha_ev_per_day=None,
        regime=state.regime_state.get("regime_rule") if state.regime_state else None,
    )


def run_live_shadow_session(
    futures_provider: FuturesDataProvider,
    instrument: str,
    level,
    mode: LiveShadowMode,
    data_source: str,
    proposal_generator: Callable[[MarketState], TradeProposal | None] | None = None,
    no_trade_state_builder: Callable[[MarketState], TradeState] | None = None,
    no_trade_thresholds: NoTradeThresholds | None = None,
    ledger: LiveShadowLedger | None = None,
    status_path: str | Path = DEFAULT_STATUS_PATH,
) -> LiveShadowSessionStatus:
    if data_source not in DATA_SOURCES:
        raise ValueError(f"data_source must be one of {DATA_SOURCES}, got {data_source!r}")

    ledger = ledger or LiveShadowLedger()
    thresholds = no_trade_thresholds or NoTradeThresholds()
    build_no_trade_state = no_trade_state_builder or _default_no_trade_state

    started_at = dt.datetime.now(dt.timezone.utc)
    counters = {"n_events": 0, "n_proposals": 0}

    def _status(state: SessionState, message: str = "") -> LiveShadowSessionStatus:
        now = dt.datetime.now(dt.timezone.utc)
        status = LiveShadowSessionStatus(
            mode=mode.value, state=state.value, data_source=data_source,
            provider_name=getattr(futures_provider, "name", None),
            started_at=started_at.isoformat(),
            last_event_at=now.isoformat() if counters["n_events"] else None,
            n_events=counters["n_events"], n_proposals=counters["n_proposals"], message=message,
        )
        status.save(status_path)
        return status

    _status(SessionState.STARTING, "subscribing to live provider")

    def on_message(payload: dict) -> None:
        counters["n_events"] += 1
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = dt.datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = dt.datetime.now(dt.timezone.utc)

        state = build_market_state(payload, timestamp=timestamp)
        no_trade_state = build_no_trade_state(state)
        eligibility = evaluate_trade_eligibility(no_trade_state, thresholds)

        if eligibility.eligible and proposal_generator is not None:
            proposal = proposal_generator(state)
            if proposal is not None:
                ledger.record_proposal(proposal)
                counters["n_proposals"] += 1

    try:
        handle = futures_provider.subscribe_live(instrument, level, on_message)
        handle.close()
    except Exception as exc:  # noqa: BLE001 - any real-world provider failure reports ERROR, never a fabricated RUNNING
        return _status(SessionState.ERROR, f"{type(exc).__name__}: {exc}")

    return _status(SessionState.STOPPED, "subscription finished")


def get_live_shadow_status(status_path: str | Path = DEFAULT_STATUS_PATH) -> LiveShadowSessionStatus:
    return LiveShadowSessionStatus.load(status_path)


def stop_live_shadow_session(status_path: str | Path = DEFAULT_STATUS_PATH) -> LiveShadowSessionStatus:
    current = get_live_shadow_status(status_path)
    stopped = LiveShadowSessionStatus(
        mode=current.mode, state=SessionState.STOPPED.value, data_source=current.data_source,
        provider_name=current.provider_name, started_at=current.started_at,
        last_event_at=current.last_event_at, n_events=current.n_events, n_proposals=current.n_proposals,
        message="stopped by operator request",
    )
    stopped.save(status_path)
    return stopped
