"""Examples are advertised API surface — run them all, as tests.

Each file in ``examples/`` is a promise to the reader: "the API in this
script exists and produces this output on a fresh install." A broken
example is a docs defect, and docs defects must fail CI like any other
regression.  Every example is:

  1. compiled (``py_compile`` — syntax must hold under the repo floor
     ``requires-python``), and
  2. executed as a subprocess under the repo's own package (PYTHONPATH
     pins ``src/`` so the worktree checkout is exercised, not whatever an
     installed ``provably`` happens to shadow it), asserting exit status 0,
     no traceback, and the semantic markers listed per file (pinned from
     the real outputs at consolidation, lane rsi-provably2, 2026-10-01).

Markers are chosen from solver-deterministic, human-facing claim lines
(``[Q.E.D.]``/``[DISPROVED]`` verdicts and arithmetic results), never
from timing lines or solver-chosen counterexample values.
"""

from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
SRC = REPO_ROOT / "src"

# Per-example deterministic markers (substrings of stdout).
MARKERS: dict[str, list[str]] = {
    "basic.py": [
        "Certificate: [Q.E.D.] safe_abs",
        "=== 2. Counterexample detected ===",
        "VerificationError raised as expected",
        "safe_abs(-7) = 7",
        "clamp(15, 0, 10) = 10",
    ],
    "compositionality.py": [
        "quarter (via safe_half contract): [Q.E.D.] quarter",
        "quarter(8.0) = 2.0",
        "All functions proven: True",
        "bad_quarter (no contract): translation_error",
        "unit_to_percent(0.75) = 75.0",
        "percent_to_unit(75.0) = 0.75",
    ],
    "refinement_types.py": [
        "nonneg_double: [Q.E.D.] nonneg_double",
        "nonneg_double(5) = 10",
        "to_unit: [Q.E.D.] to_unit",
        "lerp_unit(0.2, 0.8, 0.5) = 0.5",
        "safe_normalize: [Q.E.D.] safe_normalize",
        "Status: counterexample",
    ],
    "safety_critical.py": [
        "All invariants proven: True",
    ],
}

EXAMPLE_FILES = sorted(p.name for p in EXAMPLES_DIR.glob("*.py"))


def test_examples_present() -> None:
    """Known-positive for the parametrization: the family is not empty."""
    assert EXAMPLE_FILES, "examples/ vanished"
    assert {"basic.py", "compositionality.py", "refinement_types.py", "safety_critical.py"} <= set(
        EXAMPLE_FILES
    )


def test_markers_map_is_total_and_sound() -> None:
    """Every documented marker belongs to a file that exists (stale-key drift)."""
    assert set(MARKERS) <= set(EXAMPLE_FILES), (
        f"marker map lists removed examples: {sorted(set(MARKERS) - set(EXAMPLE_FILES))}"
    )


@pytest.mark.parametrize("example", EXAMPLE_FILES)
def test_example_compiles(example: str) -> None:
    py_compile.compile(str(EXAMPLES_DIR / example), doraise=True)


@pytest.mark.parametrize("example", EXAMPLE_FILES)
def test_example_runs_clean(example: str) -> None:
    path = EXAMPLES_DIR / example
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        f"example {example} exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout[-2000:]}\n--- stderr ---\n{proc.stderr[-2000:]}"
    )
    assert "Traceback" not in proc.stdout and "Traceback" not in proc.stderr, (
        f"example {example} printed a traceback while exiting 0:\n"
        f"--- stdout ---\n{proc.stdout[-2000:]}\n--- stderr ---\n{proc.stderr[-2000:]}"
    )
    for marker in MARKERS.get(example, []):
        assert marker in proc.stdout, (
            f"example {example} no longer prints advertised line {marker!r}; "
            f"if the change is intended, update MARKERS with the example"
        )
