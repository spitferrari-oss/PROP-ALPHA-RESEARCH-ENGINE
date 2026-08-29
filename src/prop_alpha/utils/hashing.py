"""Reproducibility helpers (spec §74 Experiment Tracker, §75 Reproducibility).

Every research run must be traceable to: dataset hash, code version (git
commit), config hash, and random seed.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def hash_file(path: str | Path) -> str:
    return hash_bytes(Path(path).read_bytes())


def hash_dict(d: dict) -> str:
    import json

    return hash_bytes(json.dumps(d, sort_keys=True, default=str).encode())


def git_commit_hash(cwd: str | Path = ".") -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()[:12]
    except Exception:
        return "unknown"


def make_experiment_id(prefix: str = "EXP") -> str:
    import datetime

    now = datetime.datetime.now()
    suffix = hashlib.sha256(now.isoformat().encode()).hexdigest()[:8]
    return f"{prefix}-{now.year}-{suffix}"
