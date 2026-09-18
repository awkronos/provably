"""The SOTA bench must not leave tracked scratch contracts behind.

``scripts/sota_bench.py::_load_contract_fresh`` writes
``scripts/_sota_contract_<i>.py`` per benchmark iteration so provably's L0
cache (keyed on ``inspect.getsource``) takes a genuine miss, and
``_cleanup_contract_files`` removes them at bench end. An interrupted run
committed 30 of them; the code map read the family as six mutually
near-duplicate orphan twins (2026-09-18 workspace analysis,
``projects/provably/scripts`` family, 6 files / 15 pairs).

This test is the ratchet: the generator, not the index, owns those files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_scratch_contracts() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "scripts/_sota_contract_*.py"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def test_no_generated_bench_contract_is_tracked() -> None:
    assert _tracked_scratch_contracts() == []


def test_the_generator_still_owns_the_scratch_file_shape() -> None:
    """Known-positive for the check above: the producer really does write
    this path, so an empty ``git ls-files`` result means "cleaned up", not
    "the pattern stopped matching anything".
    """
    source = (_REPO_ROOT / "scripts" / "sota_bench.py").read_text()
    assert 'f"_sota_contract_{counter}.py"' in source
    assert '"_sota_contract_*.py"' in source
