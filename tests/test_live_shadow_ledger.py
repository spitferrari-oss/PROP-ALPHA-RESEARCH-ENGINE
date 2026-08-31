import datetime as dt

from prop_alpha.live_shadow.feedback import apply_feedback
from prop_alpha.live_shadow.ledger import LiveShadowLedger
from prop_alpha.live_shadow.proposal import ProposalStatus, make_proposal

_NOW = dt.datetime(2024, 1, 2, 15, 30, tzinfo=dt.timezone.utc)


def _proposal():
    return make_proposal(timestamp=_NOW, instrument="ES", direction="LONG", entry_price=4500.0, rationale="test")


def test_read_all_on_missing_file_returns_empty_list(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "nonexistent.jsonl")
    assert ledger.read_all() == []


def test_record_proposal_round_trips(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")
    proposal = _proposal()
    ledger.record_proposal(proposal)

    records = ledger.read_proposals()
    assert len(records) == 1
    assert records[0]["kind"] == "PROPOSAL"
    assert records[0]["proposal_id"] == proposal.proposal_id
    assert records[0]["status"] == "PENDING"
    assert records[0]["instrument"] == "ES"


def test_record_feedback_round_trips(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")
    proposal = _proposal()
    _, feedback = apply_feedback(proposal, ProposalStatus.APPROVED, reviewer="alice", timestamp=_NOW)
    ledger.record_feedback(feedback)

    records = ledger.read_feedback()
    assert len(records) == 1
    assert records[0]["kind"] == "FEEDBACK"
    assert records[0]["decision"] == "APPROVED"
    assert records[0]["reviewer"] == "alice"


def test_read_all_returns_both_kinds_in_append_order(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")
    proposal = _proposal()
    ledger.record_proposal(proposal)
    _, feedback = apply_feedback(proposal, ProposalStatus.REJECTED, reviewer="bob", timestamp=_NOW)
    ledger.record_feedback(feedback)

    records = ledger.read_all()
    assert [r["kind"] for r in records] == ["PROPOSAL", "FEEDBACK"]


def test_ledger_is_append_only_across_two_instances(tmp_path):
    path = tmp_path / "ledger.jsonl"
    LiveShadowLedger(path=path).record_proposal(_proposal())
    LiveShadowLedger(path=path).record_proposal(_proposal())
    assert len(LiveShadowLedger(path=path).read_proposals()) == 2


def test_read_proposals_excludes_feedback_records(tmp_path):
    ledger = LiveShadowLedger(path=tmp_path / "ledger.jsonl")
    proposal = _proposal()
    ledger.record_proposal(proposal)
    _, feedback = apply_feedback(proposal, ProposalStatus.APPROVED, reviewer="alice", timestamp=_NOW)
    ledger.record_feedback(feedback)

    assert len(ledger.read_proposals()) == 1
    assert len(ledger.read_feedback()) == 1
