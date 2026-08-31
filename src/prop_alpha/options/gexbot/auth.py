"""GEXBOT API key resolution (extension spec §25): "Non inserire API keys
nel repository." The `GEXBOT_API_KEY` environment variable, or an
explicitly injected value (for testing), are the only sources — never
hardcoded in config or code.
"""
from __future__ import annotations

import os

GEXBOT_API_KEY_ENV = "GEXBOT_API_KEY"


def resolve_api_key(explicit: str | None = None) -> str:
    api_key = explicit or os.environ.get(GEXBOT_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"No GEXBOT API key: pass api_key= or set the {GEXBOT_API_KEY_ENV} environment "
            f"variable. Never hardcode it in config or code (extension §25/§98)."
        )
    return api_key
