"""Research Constitution control system (hardening pass Blocker A,
"Constitution API").

The hash is computed over `research_constitution.yaml`'s raw bytes and
stored only in the separate lock file (`research_constitution.lock.yaml`)
— never inside the file it hashes, so the hash can never be self-
consistent by construction (a tampered constitution always fails
`verify_constitution`, it can never "fix itself up" by also editing its
own embedded hash).

`assert_constitution_valid()` is the single function every governance-
gated CLI command calls before doing meaningful work (see `cli.py`'s
`_require_valid_constitution` wrapper). It raises `ConstitutionError` —
never returns a "degraded but continuing" value — on any of: malformed
YAML, missing lock file, hash mismatch, version mismatch, or ID mismatch.
There is no silent degraded mode; a command that needs the Constitution
either gets a valid one or does not run.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONSTITUTION_PATH = Path("config/research_constitution.yaml")
DEFAULT_LOCK_PATH = Path("config/research_constitution.lock.yaml")


class ConstitutionError(RuntimeError):
    """Raised by `assert_constitution_valid()` — a hard failure, not a
    warning. Callers must not catch this to "continue anyway."
    """


def load_constitution(path: str | Path = DEFAULT_CONSTITUTION_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        raise ConstitutionError(f"Constitution file not found: {path}")
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConstitutionError(f"Constitution file is malformed YAML: {exc}") from exc
    if not isinstance(data, dict) or "constitution" not in data:
        raise ConstitutionError(f"Constitution file {path} is missing the top-level 'constitution' key.")
    return data


def calculate_constitution_hash(path: str | Path = DEFAULT_CONSTITUTION_PATH) -> str:
    path = Path(path)
    if not path.exists():
        raise ConstitutionError(f"Constitution file not found: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_constitution_lock(path: str | Path = DEFAULT_LOCK_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        raise ConstitutionError(f"Constitution lock file not found: {path}")
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConstitutionError(f"Constitution lock file is malformed YAML: {exc}") from exc
    if not isinstance(data, dict) or "constitution_lock" not in data:
        raise ConstitutionError(f"Lock file {path} is missing the top-level 'constitution_lock' key.")
    return data["constitution_lock"]


@dataclass(frozen=True)
class ConstitutionVerificationResult:
    valid: bool
    integrity_ok: bool
    lockfile_present: bool
    version_match: bool
    id_match: bool
    constitution_id: str | None
    constitution_version: str | None
    computed_hash: str | None
    locked_hash: str | None
    errors: tuple[str, ...] = field(default_factory=tuple)


def verify_constitution(
    constitution_path: str | Path = DEFAULT_CONSTITUTION_PATH,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> ConstitutionVerificationResult:
    """Never raises — collects every problem found and returns them, so
    `get_constitution_status()`/`pae constitution status` can show a full
    diagnosis rather than stopping at the first error. `assert_
    constitution_valid()` is what turns a bad result into a hard failure.
    """
    errors: list[str] = []
    constitution_id = constitution_version = computed_hash = locked_hash = None
    lockfile_present = False
    integrity_ok = False
    version_match = False
    id_match = False

    try:
        data = load_constitution(constitution_path)
        body = data["constitution"]
        constitution_id = body.get("id")
        constitution_version = body.get("version")
    except ConstitutionError as exc:
        errors.append(str(exc))
        return ConstitutionVerificationResult(
            valid=False, integrity_ok=False, lockfile_present=False, version_match=False, id_match=False,
            constitution_id=None, constitution_version=None, computed_hash=None, locked_hash=None,
            errors=tuple(errors),
        )

    try:
        computed_hash = calculate_constitution_hash(constitution_path)
    except ConstitutionError as exc:
        errors.append(str(exc))

    try:
        lock = load_constitution_lock(lock_path)
        lockfile_present = True
    except ConstitutionError as exc:
        errors.append(str(exc))
        lock = {}

    if lockfile_present:
        locked_hash = lock.get("sha256")
        if computed_hash is not None and locked_hash is not None:
            integrity_ok = computed_hash == locked_hash
            if not integrity_ok:
                errors.append(
                    f"Constitution hash mismatch: file hashes to {computed_hash}, "
                    f"lock file expects {locked_hash}. The constitution has been modified "
                    f"without regenerating its lock (see docs/constitution_amendment_process.md)."
                )
        elif locked_hash is None:
            errors.append("Lock file is missing its 'sha256' field.")

        locked_version = lock.get("version")
        version_match = locked_version == constitution_version
        if not version_match:
            errors.append(
                f"Constitution version mismatch: file declares {constitution_version!r}, "
                f"lock file expects {locked_version!r}."
            )

        locked_id = lock.get("constitution_id")
        id_match = locked_id == constitution_id
        if not id_match:
            errors.append(
                f"Constitution ID mismatch: file declares {constitution_id!r}, "
                f"lock file expects {locked_id!r}."
            )

    valid = lockfile_present and integrity_ok and version_match and id_match and not any(
        "malformed" in e or "not found" in e for e in errors
    )

    return ConstitutionVerificationResult(
        valid=valid, integrity_ok=integrity_ok, lockfile_present=lockfile_present,
        version_match=version_match, id_match=id_match,
        constitution_id=constitution_id, constitution_version=constitution_version,
        computed_hash=computed_hash, locked_hash=locked_hash, errors=tuple(errors),
    )


def get_constitution_status(
    constitution_path: str | Path = DEFAULT_CONSTITUTION_PATH,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> dict:
    """Plain-dict summary for CLI rendering and for embedding into audit/
    experiment provenance records (`constitution.id`/`.version`/`.sha256`).
    """
    result = verify_constitution(constitution_path, lock_path)
    return {
        "id": result.constitution_id,
        "version": result.constitution_version,
        "hash": result.computed_hash,
        "integrity": "PASS" if result.integrity_ok else "FAIL",
        "lockfile": "PASS" if result.lockfile_present else "FAIL",
        "version_check": "PASS" if result.version_match else "FAIL",
        "id_check": "PASS" if result.id_match else "FAIL",
        "status": "CONSTITUTION VALID" if result.valid else "CONSTITUTION INVALID",
        "errors": list(result.errors),
    }


def assert_constitution_valid(
    constitution_path: str | Path = DEFAULT_CONSTITUTION_PATH,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> ConstitutionVerificationResult:
    """The hard gate. Raises `ConstitutionError` with every reason found
    if the Constitution is not valid; returns the passing result
    otherwise. Callers (CLI pre-checks) must let `ConstitutionError`
    propagate — never catch-and-continue.
    """
    result = verify_constitution(constitution_path, lock_path)
    if not result.valid:
        reasons = "\n".join(f"  - {e}" for e in result.errors) or "  - unknown validation failure"
        raise ConstitutionError(
            "RESEARCH EXECUTION BLOCKED — Constitution verification failed:\n" + reasons
        )
    return result
