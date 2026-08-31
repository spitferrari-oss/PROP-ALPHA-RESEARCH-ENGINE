import datetime as dt

from prop_alpha.live_shadow.engine import run_live_shadow_session
from prop_alpha.live_shadow.ledger import LiveShadowLedger
from prop_alpha.live_shadow.proposal import make_proposal
from prop_alpha.market_state.vector import MarketState

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _states(n: int) -> list[MarketState]:
    return [MarketState(timestamp=_NOW + dt.timedelta(minutes=i), price_state={"close": 4500.0 + i}) for i in range(n)]


def test_run_session_counts_market_states_and_no_proposals(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")
    result = run_live_shadow_session(_states(3), proposal_generator=lambda state: None, ledger=ledger)
    assert result.n_market_states == 3
    assert result.n_proposals == 0
    assert ledger.read_proposals() == []


def test_run_session_logs_every_non_none_proposal(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")

    def generator(state: MarketState):
        if state.price_state["close"] > 4501.0:
            return make_proposal(
                timestamp=state.timestamp, instrument="ES", direction="LONG",
                entry_price=state.price_state["close"], rationale="close above 4501",
            )
        return None

    result = run_live_shadow_session(_states(4), proposal_generator=generator, ledger=ledger)
    assert result.n_market_states == 4
    assert result.n_proposals == 2  # closes 4502, 4503
    assert len(ledger.read_proposals()) == 2


def test_run_session_empty_stream(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")
    result = run_live_shadow_session([], proposal_generator=lambda state: None, ledger=ledger)
    assert result.n_market_states == 0
    assert result.n_proposals == 0
    assert result.proposals == []


def test_run_session_result_includes_proposal_objects(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")

    def generator(state: MarketState):
        return make_proposal(
            timestamp=state.timestamp, instrument="ES", direction="SHORT",
            entry_price=state.price_state["close"], rationale="always propose",
        )

    result = run_live_shadow_session(_states(2), proposal_generator=generator, ledger=ledger)
    assert len(result.proposals) == 2
    assert all(p.instrument == "ES" for p in result.proposals)
