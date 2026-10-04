"""Provably test configuration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# Deliberate never-firing no-op — pinned by
# test_final_coverage.TestRequiresZ3MarkerPinnedNoOp.  8fc50d14 (2026-02-28)
# made z3-solver a hard dependency and rewrote skipif(not HAS_Z3) ->
# skipif(False) while keeping the marker's ~35 call sites across 11 test
# modules, so z3-absence ERRORS via the package's hard `import z3` instead
# of silently skipping.  Do NOT flip the condition; removing the dead marker
# is the separate P3 census hand-off (U1004-PCOV95).
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
