import pytest

from prop_alpha.governance.constitution import (
    ConstitutionError,
    assert_constitution_valid,
    calculate_constitution_hash,
    get_constitution_status,
    load_constitution,
    load_constitution_lock,
    verify_constitution,
)

_REAL_CONSTITUTION = "config/research_constitution.yaml"
_REAL_LOCK = "config/research_constitution.lock.yaml"


def test_load_constitution_returns_dict_with_top_level_key():
    data = load_constitution(_REAL_CONSTITUTION)
    assert "constitution" in data
    assert data["constitution"]["id"] == "PARE-RESEARCH-CONSTITUTION"


def test_load_constitution_missing_file_raises():
    with pytest.raises(ConstitutionError, match="not found"):
        load_constitution("config/does_not_exist.yaml")


def test_load_constitution_malformed_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("constitution: [unterminated")
    with pytest.raises(ConstitutionError, match="malformed"):
        load_constitution(bad)


def test_load_constitution_missing_top_level_key_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not_constitution: {}")
    with pytest.raises(ConstitutionError, match="top-level"):
        load_constitution(bad)


def test_calculate_constitution_hash_is_deterministic():
    a = calculate_constitution_hash(_REAL_CONSTITUTION)
    b = calculate_constitution_hash(_REAL_CONSTITUTION)
    assert a == b
    assert len(a) == 64  # full SHA256 hex digest


def test_load_constitution_lock_returns_inner_dict():
    lock = load_constitution_lock(_REAL_LOCK)
    assert lock["constitution_id"] == "PARE-RESEARCH-CONSTITUTION"
    assert "sha256" in lock


def test_real_constitution_verifies_against_its_real_lock():
    result = verify_constitution(_REAL_CONSTITUTION, _REAL_LOCK)
    assert result.valid is True
    assert result.errors == ()


def test_real_constitution_assert_valid_does_not_raise():
    result = assert_constitution_valid(_REAL_CONSTITUTION, _REAL_LOCK)
    assert result.valid is True


def test_get_constitution_status_reports_valid_for_real_files():
    status = get_constitution_status(_REAL_CONSTITUTION, _REAL_LOCK)
    assert status["status"] == "CONSTITUTION VALID"
    assert status["integrity"] == "PASS"
    assert status["lockfile"] == "PASS"


# --- tampering scenarios, always against tmp_path fixture copies, never the real files ---

def _write_pair(tmp_path, constitution_text, lock_text):
    constitution_path = tmp_path / "research_constitution.yaml"
    lock_path = tmp_path / "research_constitution.lock.yaml"
    constitution_path.write_text(constitution_text)
    lock_path.write_text(lock_text)
    return constitution_path, lock_path


_MINIMAL_CONSTITUTION = """\
constitution:
  id: TEST-CONSTITUTION
  version: 1.0.0
"""


def test_verify_fails_with_missing_lock_file(tmp_path):
    constitution_path = tmp_path / "c.yaml"
    constitution_path.write_text(_MINIMAL_CONSTITUTION)
    result = verify_constitution(constitution_path, tmp_path / "nonexistent_lock.yaml")
    assert result.valid is False
    assert result.lockfile_present is False


def test_verify_fails_with_tampered_content_hash_mismatch(tmp_path):
    from prop_alpha.governance.constitution import calculate_constitution_hash as _hash

    constitution_path, lock_path = _write_pair(
        tmp_path, _MINIMAL_CONSTITUTION,
        "constitution_lock:\n  constitution_id: TEST-CONSTITUTION\n  version: 1.0.0\n"
        "  sha256: 0000000000000000000000000000000000000000000000000000000000000000\n",
    )
    real_hash = _hash(constitution_path)
    assert real_hash != "0000000000000000000000000000000000000000000000000000000000000000"
    result = verify_constitution(constitution_path, lock_path)
    assert result.valid is False
    assert result.integrity_ok is False
    assert any("hash mismatch" in e for e in result.errors)


def test_verify_fails_with_version_mismatch(tmp_path):
    from prop_alpha.governance.constitution import calculate_constitution_hash as _hash

    constitution_path = tmp_path / "c.yaml"
    constitution_path.write_text(_MINIMAL_CONSTITUTION)
    real_hash = _hash(constitution_path)
    lock_path = tmp_path / "c.lock.yaml"
    lock_path.write_text(
        f"constitution_lock:\n  constitution_id: TEST-CONSTITUTION\n  version: 9.9.9\n  sha256: {real_hash}\n"
    )
    result = verify_constitution(constitution_path, lock_path)
    assert result.valid is False
    assert result.version_match is False


def test_verify_fails_with_id_mismatch(tmp_path):
    from prop_alpha.governance.constitution import calculate_constitution_hash as _hash

    constitution_path = tmp_path / "c.yaml"
    constitution_path.write_text(_MINIMAL_CONSTITUTION)
    real_hash = _hash(constitution_path)
    lock_path = tmp_path / "c.lock.yaml"
    lock_path.write_text(
        f"constitution_lock:\n  constitution_id: WRONG-ID\n  version: 1.0.0\n  sha256: {real_hash}\n"
    )
    result = verify_constitution(constitution_path, lock_path)
    assert result.valid is False
    assert result.id_match is False


def test_assert_constitution_valid_raises_on_tampered_pair(tmp_path):
    constitution_path, lock_path = _write_pair(
        tmp_path, _MINIMAL_CONSTITUTION,
        "constitution_lock:\n  constitution_id: TEST-CONSTITUTION\n  version: 1.0.0\n"
        "  sha256: 0000000000000000000000000000000000000000000000000000000000000000\n",
    )
    with pytest.raises(ConstitutionError, match="RESEARCH EXECUTION BLOCKED"):
        assert_constitution_valid(constitution_path, lock_path)


def test_verify_does_not_raise_even_when_invalid(tmp_path):
    # verify_constitution is the non-raising diagnostic form; only
    # assert_constitution_valid raises.
    result = verify_constitution(tmp_path / "missing.yaml", tmp_path / "missing_lock.yaml")
    assert result.valid is False
