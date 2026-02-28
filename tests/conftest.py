"""Provably test configuration."""

from __future__ import annotations

import pytest

try:
    import z3  # noqa: F401

    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False

requires_z3 = pytest.mark.skipif(not HAS_Z3, reason="z3-solver not installed")


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """Clear the global proof cache before every test."""
    try:
        from provably.engine import clear_cache as _clear

        _clear()
    except ImportError:
        pass
