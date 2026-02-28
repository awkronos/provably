"""Provably test configuration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

requires_z3 = pytest.mark.skipif(False, reason="z3-solver is a hard dependency")


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    """Clear proof cache and disable disk cache for every test."""
    from provably.engine import _config
    from provably.engine import clear_cache as _clear

    old_cache_dir = _config.get("cache_dir")
    _config["cache_dir"] = None  # no disk writes during tests
    _clear()
    yield
    _config["cache_dir"] = old_cache_dir
    _clear()
