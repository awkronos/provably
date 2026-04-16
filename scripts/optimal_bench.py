"""Speed-of-light benchmark for provably.

Measures full pipeline time (provably.verify_function end-to-end) vs
bare Z3 solve time on the same SMT-LIB formula. The ratio is efficiency_pct.

Contract under test
-------------------
clamp(val, lo, hi) — float  [pre: lo <= hi]  [post: lo <= result <= hi]

This is a representative real-world contract: two comparison branches in the
body, a non-trivial precondition, a two-sided postcondition. It exercises:
  - AST parsing + source inspection
  - Z3 symbolic variable creation
  - Translator (branch IR → Z3 constraints)
  - Solver setup + negation + UNSAT check
  - ProofCertificate construction + disk-cache write

Usage
-----
    python -m scripts.optimal_bench          # from repo root
    python scripts/optimal_bench.py          # direct
    make bench                               # via Makefile target

Output
------
    /tmp/kagami-provably-bench.json
"""

from __future__ import annotations

import ast
import json
import statistics
import sys
import textwrap
import time
from pathlib import Path

import z3

# ---------------------------------------------------------------------------
# Ensure src/provably is importable when run as a script from the repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from provably.engine import clear_cache, verify_function  # noqa: E402
from provably.translator import Translator  # noqa: E402
from provably.types import make_z3_var  # noqa: E402

# ---------------------------------------------------------------------------
# Contract under test (source kept as a string — same bytes for both paths)
# ---------------------------------------------------------------------------

_CONTRACT_SOURCE = textwrap.dedent("""\
def clamp(val: float, lo: float, hi: float) -> float:
    if val < lo:
        return lo
    elif val > hi:
        return hi
    return val
""")

# Write to a real .py file so inspect.getsource works in verify_function
_BENCH_MODULE_PATH = Path(__file__).parent / "_bench_contract.py"


def _ensure_contract_file() -> None:
    """Write the contract source to a file if needed (inspect.getsource requires it)."""
    _BENCH_MODULE_PATH.write_text(_CONTRACT_SOURCE)


def _load_contract():
    """Import the clamp function from the written contract file."""
    import importlib.util
    _ensure_contract_file()
    spec = importlib.util.spec_from_file_location("_bench_contract", _BENCH_MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.clamp


# ---------------------------------------------------------------------------
# Build the SMT-LIB formula once (used identically on both paths)
# ---------------------------------------------------------------------------

def _build_smt2() -> str:
    """Return the SMT-LIB2 string that both paths solve."""
    tree = ast.parse(_CONTRACT_SOURCE)
    func_ast = tree.body[0]
    param_vars = {
        "val": make_z3_var("val", float),
        "lo":  make_z3_var("lo",  float),
        "hi":  make_z3_var("hi",  float),
    }
    param_types = {"val": float, "lo": float, "hi": float}
    translator = Translator(param_types, None, {})
    result = translator.translate(func_ast, param_vars)

    s = z3.Solver()
    # precondition: lo <= hi
    s.add(param_vars["lo"] <= param_vars["hi"])
    # body constraints from translator
    for c in result.constraints:
        s.add(c)
    # negate postcondition: NOT (lo <= result AND result <= hi)
    ret = result.return_expr
    s.add(z3.Not(z3.And(ret >= param_vars["lo"], ret <= param_vars["hi"])))
    return s.to_smt2()


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

WARMUP = 3
MEASURE = 10


def _measure_pipeline_ns(clamp_fn) -> list[int]:
    """Time the full provably.verify_function pipeline (cache disabled)."""
    pre  = lambda val, lo, hi: lo <= hi          # noqa: E731
    post = lambda val, lo, hi, result: (result >= lo) & (result <= hi)  # noqa: E731
    samples: list[int] = []
    for i in range(WARMUP + MEASURE):
        clear_cache()
        t0 = time.perf_counter_ns()
        cert = verify_function(clamp_fn, pre=pre, post=post)
        t1 = time.perf_counter_ns()
        assert cert.verified, f"pipeline did not verify: {cert}"
        if i >= WARMUP:
            samples.append(t1 - t0)
    return samples


def _measure_bare_z3_ns(smt2: str) -> list[int]:
    """Time bare Z3 solve on the same SMT-LIB formula."""
    samples: list[int] = []
    for i in range(WARMUP + MEASURE):
        s = z3.Solver()
        s.from_string(smt2)
        t0 = time.perf_counter_ns()
        result = s.check()
        t1 = time.perf_counter_ns()
        assert result == z3.unsat, f"bare Z3 check expected unsat, got {result}"
        if i >= WARMUP:
            samples.append(t1 - t0)
    return samples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> dict:
    smt2 = _build_smt2()
    clamp_fn = _load_contract()

    print(f"provably optimal_bench — clamp contract ({WARMUP}w + {MEASURE} iterations each)")
    print(f"z3 version: {z3.get_version_string()}")

    pipeline_ns = _measure_pipeline_ns(clamp_fn)
    bare_z3_ns  = _measure_bare_z3_ns(smt2)

    pipeline_median_s = statistics.median(pipeline_ns) / 1e9
    bare_z3_median_s  = statistics.median(bare_z3_ns)  / 1e9
    efficiency_pct    = (bare_z3_median_s / pipeline_median_s) * 100.0

    result = {
        "efficiency_pct": round(efficiency_pct, 2),
        "actual":         round(pipeline_median_s, 8),
        "theoretical":    round(bare_z3_median_s,  8),
        "unit":           "seconds",
        "workload":       "verify_pipeline_vs_bare_z3",
    }

    out_path = Path("/tmp/kagami-provably-bench.json")
    out_path.write_text(json.dumps(result, indent=2))

    print(f"  pipeline (full provably):  {pipeline_median_s*1000:.3f} ms  (median of {MEASURE})")
    print(f"  bare Z3 solve:             {bare_z3_median_s*1000:.3f} ms  (median of {MEASURE})")
    print(f"  efficiency:                {efficiency_pct:.1f}%")
    print(f"  sidecar written:           {out_path}")

    return result


if __name__ == "__main__":
    run()
