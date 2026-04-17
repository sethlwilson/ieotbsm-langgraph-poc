"""Ensure repository root is on sys.path so ``network`` can be imported."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root() -> Path:
    """``services/trust_api/trust_api`` → repo root (three levels up)."""
    here = Path(__file__).resolve().parent
    root = here.parent.parent.parent
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)
    return root
