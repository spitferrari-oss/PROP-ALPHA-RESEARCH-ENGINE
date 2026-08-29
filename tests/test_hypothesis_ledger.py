from prop_alpha.discovery.hypothesis import Hypothesis, HypothesisLedger


def _hypothesis(hid="H1", status="BACKTESTED"):
    return Hypothesis(
        hypothesis_id=hid, date="2026-08-29", author="test", market="NQ",
        mechanism="test mechanism", hypothesis="test hypothesis",
        economic_rationale="test rationale", expected_behavior="test behavior",
        features=["f1"], expected_regimes=["ALL"], expected_failure_modes=["LOW_SAMPLE"],
        test_plan="test plan", result="test result", status=status,
    )


def test_append_and_read_roundtrip(tmp_path):
    ledger = HypothesisLedger(tmp_path / "ledger.jsonl")
    ledger.append(_hypothesis("H1"))
    entries = ledger.read_all()
    assert len(entries) == 1
    assert entries[0]["hypothesis_id"] == "H1"
    assert entries[0]["status"] == "BACKTESTED"


def test_append_many(tmp_path):
    ledger = HypothesisLedger(tmp_path / "sub" / "ledger.jsonl")
    ledger.append_many([_hypothesis("H1"), _hypothesis("H2"), _hypothesis("H3")])
    entries = ledger.read_all()
    assert [e["hypothesis_id"] for e in entries] == ["H1", "H2", "H3"]


def test_read_all_on_missing_file_returns_empty(tmp_path):
    ledger = HypothesisLedger(tmp_path / "does_not_exist.jsonl")
    assert ledger.read_all() == []


def test_append_never_overwrites_prior_entries(tmp_path):
    ledger = HypothesisLedger(tmp_path / "ledger.jsonl")
    ledger.append(_hypothesis("H1"))
    ledger2 = HypothesisLedger(tmp_path / "ledger.jsonl")
    ledger2.append(_hypothesis("H2"))
    entries = ledger.read_all()
    assert [e["hypothesis_id"] for e in entries] == ["H1", "H2"]


def test_directory_created_automatically(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "ledger.jsonl"
    ledger = HypothesisLedger(nested)
    ledger.append(_hypothesis("H1"))
    assert nested.exists()
