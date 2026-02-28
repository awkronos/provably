"""Provably test configuration."""

from __future__ import annotations

import pytest

# z3-solver is a hard dependency — always available
requires_z3 = pytest.mark.skipif(False, reason="z3-solver is a hard dependency")


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """Clear the global proof cache before every test."""
    from provably.engine import clear_cache as _clear

    _clear()
