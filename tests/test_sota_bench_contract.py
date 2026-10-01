"""Output-contract pin for ``scripts/sota_bench.py`` (the SOTA sidecar).

bench-zero-is-plumbing-first: when a bench consumer shows zero/drift, the
first question is "did the producer's wire keys change?", not "did the
library get slower?".  The sidecar at ``SIDECAR_PATH`` is consumed by the
libraries-heartbeat and advertised in README.md ("{"actual": ..., "sota":
..., "sota_name": ..., "efficiency_pct": ..., "competitors": [...]}"), so
the key names, row shape, and score polarity are public surface.  This
module pins them against the producer itself:

* the real producer is exercised for one fast competitor (``z3-direct``,
  z3-solver is a hard dependency) so a "passing schema test" can never be
  a fake-only artifact — the known-positive;
* the composition path (``run()``) is exercised with fakes that emit
  byte-for-byte the same row shapes the real benches emit (an unfaithful
  fake would hide exactly the drift this test exists to catch);
* README's documented sample keys must all be present on the wire;
* polarity: ``efficiency_pct > 100`` must mean provably is *faster* than
  the fastest competitor (README claim + "lower is better" unit);
* fail-closed: if provably itself fails, ``run()`` exits 1 and writes no
  sidecar — consumers never see a half-updated artifact.

The sidecar *path* vs README is already pinned by
``tests/test_docs_consistency.py``; nothing is re-pinned here.
"""

from __future__ import annotations

import importlib.util
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SOTA_BENCH = REPO_ROOT / "scripts" / "sota_bench.py"
README = REPO_ROOT / "README.md"

# The documented, advertised set — README.md bench section sample line.
README_SAMPLE_KEYS = {"actual", "sota", "sota_name", "efficiency_pct", "competitors"}

# Full producer-emitted top-level schema (superset of the advertised sample).
SIDECAR_KEYS = {
    "library",
    "workload",
    "unit",
    "actual",
    "sota",
    "sota_name",
    "sota_version",
    "efficiency_pct",
    "competitors",
    "timestamp",
    "fairness_notes",
}

ROW_KEYS = {"name", "version", "wall_sec", "artifact", "ok"}

# run() executes the benches list in this fixed order; consumers index rows
# by position and name, so the order is part of the wire contract.
COMPETITOR_ORDER = [
    "provably",
    "halmos",
    "pysmt-z3",
    "cvc5",
    "z3-direct-python",
    "solc-SMTChecker",
]


def _load_bench_module() -> Any:
    spec = importlib.util.spec_from_file_location("_sota_bench_under_test", SOTA_BENCH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ok_row(name: str, wall: float, artifact: str, version: str = "fake") -> dict[str, Any]:
    """Byte-for-byte the success-row shape emitted by every real bench_*."""
    return {"name": name, "version": version, "wall_sec": wall, "artifact": artifact, "ok": True}


def _fail_row(name: str, error: str, version: str = "not-installed") -> dict[str, Any]:
    """The failure-row shape emitted by every real bench_*."""
    return {
        "name": name,
        "version": version,
        "wall_sec": None,
        "artifact": None,
        "ok": False,
        "error": error,
    }


@pytest.fixture()
def bench_mod() -> Any:
    return _load_bench_module()


@pytest.fixture()
def sidecar_dir(tmp_path: Path, bench_mod: Any) -> Path:
    monkeypath = tmp_path / "kagami-provably-bench.json"
    bench_mod.SIDECAR_PATH = monkeypath
    return monkeypath


def _install_fakes(bench_mod: Any, rows: dict[str, dict[str, Any]]) -> None:
    for fn_name, row in rows.items():
        setattr(bench_mod, fn_name, lambda _r=row: dict(_r))


# ---------------------------------------------------------------------------
# Known-positive: the REAL producer emits rows of the pinned shape
# ---------------------------------------------------------------------------


def test_real_bench_z3_direct_row_matches_pinned_row_shape(bench_mod: Any) -> None:
    """Never conclude the schema from fakes alone: run one real competitor.

    z3-direct is the cheapest bench (raw solver API, ~30 fresh solver
    instances, sub-second) and z3-solver is a hard dependency, so this is
    an unconditional known-positive for ``ROW_KEYS``.
    """
    row = bench_mod.bench_z3_direct()
    assert set(row.keys()) == ROW_KEYS, (
        "real producer row shape drifted from the pinned contract; the fake-"
        "based tests below are only meaningful while they mirror this shape"
    )
    assert row["name"] == "z3-direct-python"
    assert row["ok"] is True and isinstance(row["wall_sec"], float) and row["wall_sec"] > 0
    assert row["artifact"] == "UNSAT witness (raw Z3 API, no Lean)"
    assert isinstance(row["version"], str) and row["version"]


def test_readme_sample_line_still_documents_the_wire(bench_mod: Any) -> None:
    """Wire-key diff: every key the README advertises must exist on the sidecar."""
    readme = README.read_text(encoding="utf-8")
    m = re.search(r"^\s*#\s*\{(.+?)\}\s*$", readme, re.MULTILINE)
    assert m is not None, (
        "README's documented sidecar sample line disappeared; "
        "update this test and the README together"
    )
    documented = set(re.findall(r'"([a-z_]+)":', m.group(1)))
    assert documented == README_SAMPLE_KEYS, (
        f"README advertises {sorted(documented)} but this test pins {sorted(README_SAMPLE_KEYS)}"
    )


# ---------------------------------------------------------------------------
# Composition path (run()) — full sidecar schema, faked benches
# ---------------------------------------------------------------------------


def _fake_results() -> dict[str, dict[str, Any]]:
    return {
        "bench_provably": _ok_row("provably", 0.004, "SMT+Lean4"),
        "bench_halmos": _fail_row("halmos", "halmos binary not found on PATH"),
        "bench_pysmt_z3": _ok_row("pysmt-z3", 0.002, "UNSAT witness (SMT)"),
        "bench_cvc5": _ok_row("cvc5", 0.005, "UNSAT witness (SMT, LIA)"),
        "bench_z3_direct": _ok_row(
            "z3-direct-python", 0.001, "UNSAT witness (raw Z3 API, no Lean)"
        ),
        "bench_solc_smt": _fail_row(
            "solc-SMTChecker", "solc not found on PATH (brew install solidity)"
        ),
    }


def test_sidecar_top_level_schema_exact(bench_mod: Any, sidecar_dir: Path) -> None:
    _install_fakes(bench_mod, _fake_results())
    sidecar = bench_mod.run()
    assert set(sidecar.keys()) == SIDECAR_KEYS
    assert sidecar == json.loads(sidecar_dir.read_text(encoding="utf-8")), (
        "run() must write exactly the dict it returns — the file is the wire"
    )


def test_sidecar_rows_carry_pinned_shape_and_order(bench_mod: Any, sidecar_dir: Path) -> None:
    _install_fakes(bench_mod, _fake_results())
    sidecar = bench_mod.run()
    rows = sidecar["competitors"]
    assert [r["name"] for r in rows] == COMPETITOR_ORDER, "consumer-side indexing by order broke"
    for r in rows:
        if r["ok"]:
            assert set(r.keys()) == ROW_KEYS, r
        else:
            assert set(r.keys()) == ROW_KEYS | {"error"}, r
            assert r["wall_sec"] is None and r["artifact"] is None, r


def test_efficiency_score_polarity(bench_mod: Any, sidecar_dir: Path) -> None:
    """>100 must mean provably is FASTER (README); <100 slower. Formula pinned."""
    rows = _fake_results()
    # provably 4ms, fastest competitor z3-direct 1ms -> slower than SOTA
    _install_fakes(bench_mod, rows)
    slow = bench_mod.run()
    assert slow["efficiency_pct"] == pytest.approx(round(100.0 * 0.001 / 0.004, 2))
    assert slow["efficiency_pct"] < 100.0
    assert slow["sota"] == 0.001 and slow["sota_name"] == "z3-direct-python"
    assert slow["actual"] == 0.004

    # provably 0.5ms -> faster than every competitor
    rows = dict(_fake_results())
    rows["bench_provably"] = _ok_row("provably", 0.0005, "SMT+Lean4")
    _install_fakes(bench_mod, rows)
    fast = bench_mod.run()
    assert fast["efficiency_pct"] == pytest.approx(round(100.0 * 0.001 / 0.0005, 2))
    assert fast["efficiency_pct"] > 100.0


def test_unit_declares_wall_time_lower_is_better(bench_mod: Any, sidecar_dir: Path) -> None:
    """The polarity claim above is only coherent if the unit stays 'lower is better'."""
    _install_fakes(bench_mod, _fake_results())
    sidecar = bench_mod.run()
    assert sidecar["unit"] == "seconds (wall-time, lower is better)"
    assert sidecar["library"] == "provably"


def test_timestamp_is_verdict_time(bench_mod: Any, sidecar_dir: Path) -> None:
    _install_fakes(bench_mod, _fake_results())
    before = int(time.time())
    sidecar = bench_mod.run()
    assert isinstance(sidecar["timestamp"], int)
    assert before <= sidecar["timestamp"] <= int(time.time()) + 2


def test_provably_failure_is_fail_closed_no_sidecar(bench_mod: Any, sidecar_dir: Path) -> None:
    """If provably itself fails, run() must exit 1 BEFORE writing: consumers
    never observe a sidecar with a null ``actual``."""
    rows = _fake_results()
    rows["bench_provably"] = _fail_row("provably", "no samples collected", version="0.4.0")
    _install_fakes(bench_mod, rows)
    with pytest.raises(SystemExit) as excinfo:
        bench_mod.run()
    assert excinfo.value.code == 1
    assert not sidecar_dir.exists(), "fail-closed violated: partial sidecar written"


def test_no_competitor_ok_still_emits_zero_not_null(bench_mod: Any, sidecar_dir: Path) -> None:
    """With no successful competitor the contract pins sota=None/none and
    efficiency 0.0 — a consumer distinguishing 'zero' from 'absent' needs
    this documented shape to hold (bench-zero-is-plumbing-first)."""
    rows = {
        "bench_provably": _ok_row("provably", 0.004, "SMT+Lean4"),
        "bench_halmos": _fail_row("halmos", "halmos binary not found on PATH"),
        "bench_pysmt_z3": _fail_row("pysmt-z3", "pysmt not installed"),
        "bench_cvc5": _fail_row("cvc5", "cvc5 not installed"),
        "bench_z3_direct": _fail_row("z3-direct-python", "z3 import failed"),
        "bench_solc_smt": _fail_row(
            "solc-SMTChecker", "solc not found on PATH (brew install solidity)"
        ),
    }
    _install_fakes(bench_mod, rows)
    sidecar = bench_mod.run()
    assert sidecar["sota"] is None and sidecar["sota_name"] == "none"
    assert sidecar["efficiency_pct"] == 0.0
    assert sidecar["actual"] == 0.004
