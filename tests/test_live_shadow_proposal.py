import datetime as dt
from dataclasses import asdict

import pytest

from prop_alpha.live_shadow.proposal import ProposalStatus, make_proposal, proposal_from_record
from prop_alpha.market_state.vector import MarketState

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def test_make_proposal_defaults_to_pending():
    proposal = make_proposal(
        timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test",
    )
    assert proposal.status == ProposalStatus.PENDING


def test_make_proposal_naive_timestamp_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        make_proposal(
            timestamp=dt.datetime(2024, 1, 2, 15, 30), instrument="ES", direction="LONG",
            entry_price=4500.0, rationale="test",
        )


def test_make_proposal_invalid_direction_raises():
    with pytest.raises(ValueError, match="direction"):
        make_proposal(timestamp=_NOW, instrument="ES", direction="SIDEWAYS", entry_price=4500.0, rationale="test")


def test_make_proposal_deterministic_id_for_identical_inputs():
    kwargs = dict(timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test")
    p1 = make_proposal(**kwargs)
    p2 = make_proposal(**kwargs)
    assert p1.proposal_id == p2.proposal_id


def test_make_proposal_different_inputs_yield_different_ids():
    p1 = make_proposal(timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test")
    p2 = make_proposal(timestamp=_NOW, instrument="ES", direction="SHORT", entry_price=4500.0, rationale="test")
    assert p1.proposal_id != p2.proposal_id


def test_make_proposal_without_market_state_has_empty_snapshot():
    proposal = make_proposal(timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test")
    assert proposal.market_state_snapshot == {}


def test_make_proposal_with_market_state_flattens_snapshot():
    state = MarketState(timestamp=_NOW, price_state={"close": 4500.0})
    proposal = make_proposal(
        timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test",
        market_state=state,
    )
    assert proposal.market_state_snapshot == {"price_state.close": 4500.0}


def test_make_proposal_optional_fields_default_none():
    proposal = make_proposal(timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test")
    assert proposal.stop_price is None
    assert proposal.target_price is None
    assert proposal.expected_r is None
    assert proposal.model_probability is None


def test_make_proposal_carries_through_all_optional_fields():
    proposal = make_proposal(
        timestamp=_NOW, instrument="ES", direction="SHORT", entry_price=4500.0, rationale="test",
        stop_price=4520.0, target_price=4460.0, expected_r=1.5, model_probability=0.62,
    )
    assert proposal.stop_price == 4520.0
    assert proposal.target_price == 4460.0
    assert proposal.expected_r == 1.5
    assert proposal.model_probability == 0.62


def test_proposal_from_record_round_trips_through_ledger_shape():
    original = make_proposal(
        timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test",
        stop_price=4480.0, target_price=4540.0, expected_r=1.2, model_probability=0.55,
    )
    record = {"kind": "PROPOSAL", **asdict(original)}
    # ledger round-trip: dataclasses.asdict keeps datetime/Enum objects, but a real
    # ledger read comes back through json.dumps(default=str)/json.loads first, so
    # timestamp/status arrive as plain strings.
    record["timestamp"] = original.timestamp.isoformat()
    record["status"] = original.status.value

    reconstructed = proposal_from_record(record)
    assert reconstructed == original

