import datetime as dt

import pytest

from prop_alpha.live_shadow.feedback import apply_feedback
from prop_alpha.live_shadow.proposal import ProposalStatus, make_proposal

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _proposal():
    return make_proposal(timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test")


def test_apply_feedback_approved_updates_status():
    updated, feedback = apply_feedback(_proposal(), ProposalStatus.APPROVED, reviewer="alice", timestamp=_NOW)
    assert updated.status == ProposalStatus.APPROVED
    assert feedback.decision == ProposalStatus.APPROVED
    assert feedback.reviewer == "alice"


def test_apply_feedback_rejected_updates_status():
    updated, feedback = apply_feedback(_proposal(), ProposalStatus.REJECTED, reviewer="bob", timestamp=_NOW)
    assert updated.status == ProposalStatus.REJECTED


def test_apply_feedback_preserves_proposal_id():
    original = _proposal()
    updated, feedback = apply_feedback(original, ProposalStatus.APPROVED, reviewer="alice", timestamp=_NOW)
    assert updated.proposal_id == original.proposal_id
    assert feedback.proposal_id == original.proposal_id


def test_apply_feedback_does_not_mutate_original_proposal():
    original = _proposal()
    apply_feedback(original, ProposalStatus.APPROVED, reviewer="alice", timestamp=_NOW)
    assert original.status == ProposalStatus.PENDING


def test_apply_feedback_invalid_decision_raises():
    with pytest.raises(ValueError, match="decision"):
        apply_feedback(_proposal(), ProposalStatus.PENDING, reviewer="alice", timestamp=_NOW)


def test_apply_feedback_already_decided_proposal_raises():
    updated, _ = apply_feedback(_proposal(), ProposalStatus.APPROVED, reviewer="alice", timestamp=_NOW)
    with pytest.raises(ValueError, match="already"):
        apply_feedback(updated, ProposalStatus.REJECTED, reviewer="bob", timestamp=_NOW)


def test_apply_feedback_naive_timestamp_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        apply_feedback(
            _proposal(), ProposalStatus.APPROVED, reviewer="alice",
            timestamp=dt.datetime(2024, 1, 2, 15, 30),
        )


def test_apply_feedback_defaults_timestamp_to_now():
    updated, feedback = apply_feedback(_proposal(), ProposalStatus.APPROVED, reviewer="alice")
    assert feedback.timestamp.tzinfo is not None


def test_apply_feedback_carries_optional_rationale():
    _, feedback = apply_feedback(
        _proposal(), ProposalStatus.REJECTED, reviewer="alice", rationale="too far from VWAP", timestamp=_NOW,
    )
    assert feedback.rationale == "too far from VWAP"
