from prop_alpha.agents.audit import AuditEntry, AuditTrail


def _entry(experiment_id="EXP-1", decision="PASSES_ALL_EVALUATED_GATES"):
    return AuditEntry(
        date="2026-08-30", experiment_id=experiment_id, alpha_id="ALPHA_12",
        alpha_name="Opening Drive Continuation", hypothesis="test mechanism",
        dataset_hash="abc123", config_hash="def456",
        result_summary="n_trades=126, oos_ev_day=1234.56",
        decision=decision, reasons=[],
    )


def test_append_and_read_roundtrip(tmp_path):
    trail = AuditTrail(tmp_path / "audit.jsonl")
    trail.append(_entry())
    entries = trail.read_all()
    assert len(entries) == 1
    assert entries[0]["experiment_id"] == "EXP-1"
    assert entries[0]["decision"] == "PASSES_ALL_EVALUATED_GATES"


def test_append_never_overwrites(tmp_path):
    trail = AuditTrail(tmp_path / "audit.jsonl")
    trail.append(_entry("EXP-1"))
    trail.append(_entry("EXP-2", decision="RESEARCH_FAIL"))
    entries = trail.read_all()
    assert [e["experiment_id"] for e in entries] == ["EXP-1", "EXP-2"]


def test_read_all_missing_file_returns_empty(tmp_path):
    trail = AuditTrail(tmp_path / "nope.jsonl")
    assert trail.read_all() == []


def test_directory_created_automatically(tmp_path):
    nested = tmp_path / "a" / "b" / "audit.jsonl"
    trail = AuditTrail(nested)
    trail.append(_entry())
    assert nested.exists()


def test_reasons_persisted():
    entry = _entry(decision="RESEARCH_FAIL")
    entry.reasons = ["Gate X FAILED: bad", "Critic finding Y (HIGH): risky"]
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        trail = AuditTrail(Path(d) / "audit.jsonl")
        trail.append(entry)
        loaded = trail.read_all()[0]
        assert loaded["reasons"] == entry.reasons
