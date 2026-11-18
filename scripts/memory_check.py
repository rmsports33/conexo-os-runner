"""Bounded, read-only memory-check task. Repository roots are operator-configured."""
import os
from pathlib import Path
from scripts.mem_gate import TERMS, inventory, assess

ENV_REPOS = "CONEXO_MEMORY_REPOS"
MAX_REPOS = 8

def check_memory(payload):
    if set(payload) != {"type", "category"}:
        raise ValueError("memory_check accepts only type and category")
    category = payload.get("category")
    if not isinstance(category, str) or category not in TERMS:
        raise ValueError("Invalid memory category")
    configured = os.environ.get(ENV_REPOS, "")
    raw = configured.split(os.pathsep) if configured else []
    if not raw or len(raw) > MAX_REPOS or any(not x.strip() for x in raw):
        raise ValueError("Memory repositories are not configured safely")
    try:
        repos = [Path(x).resolve(strict=True) for x in raw]
        if len(set(repos)) != len(repos) or any(not p.is_dir() for p in repos):
            raise ValueError("Invalid memory repository configuration")
        result = assess(inventory(repos), category)
    except (OSError, RuntimeError, UnicodeError) as exc:
        raise ValueError("Memory lookup failed closed") from exc
    return {"repositories": [str(p) for p in repos], **result}
