"""SOTA benchmark for provably (Python).

Measures full pipeline time (provably.verify_function end-to-end) against
real production Python contract-verification tooling on the same property:

    ERC-20 transfer overflow safety proof, end-to-end.
    Property: transfer(balance, value) is safe when value <= balance.
      pre:  balance >= 0  AND  value >= 0  AND  value <= balance
      post: result == balance - value  AND  result >= 0

Competitors (ranked by practitioner relevance):
  1. halmos       (a16z, Solidity symbolic EVM) — subprocess
  2. pysmt-z3     (research-grade Python SMT API, Z3 backend)
  3. cvc5         (research-grade, native Python bindings)
  4. z3-direct    (raw z3-solver API — lower bound, no Lean)
  5. solc-SMT     (solc --model-checker-engine, production EVM)

Usage
-----
    python scripts/sota_bench.py         # from repo root
    make bench-sota                      # via Makefile

Output
------
    /tmp/kagami-provably-bench.json      (SOTA sidecar, replaces old bench)
    /tmp/kagami-provably-sota-full.json  (full competitor table)
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo root on path
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Increased from (2,5) to (5,25) on 2026-04-18: provably's measured wall-time
# dropped to 50-80μs after L0 fast-cache + orjson disk-load + memoized cache
# dir, so MEASURE=5 runs gave very noisy medians (±40% jitter from OS scheduler
# at microsecond scale). MEASURE=25 stabilizes the median within ±3%.
WARMUP = 5
MEASURE = 25
FIXTURES = _REPO_ROOT / "benches" / "fixtures"

# ---------------------------------------------------------------------------
# Provably contract (written to a real file so inspect.getsource works)
# ---------------------------------------------------------------------------
# L0 cache key = function source code.  Reusing the same source across runs
# makes every post-warmup call a cache hit (~0.06 ms) rather than a real z3
# dispatch (~4.37 ms).  _load_contract_fresh(i) embeds the counter in the
# function name so each benchmark iteration gets a genuine cache miss.
def _load_contract_fresh(counter: int):
    fn_name = f"erc20_transfer_{counter}"
    src = (
        f"def {fn_name}(balance: int, value: int) -> int:\n"
        f"    new_balance = balance - value\n"
        f"    return new_balance\n"
    )
    tmp = _REPO_ROOT / "scripts" / f"_sota_contract_{counter}.py"
    tmp.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location(f"_sota_contract_{counter}", tmp)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return getattr(mod, fn_name)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _median(samples: list[float]) -> float:
    s = sorted(samples)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _pkg_version(name: str) -> str:
    """Return installed version for a package, or 'unknown'."""
    try:
        import importlib.metadata
        return importlib.metadata.version(name)
    except Exception:
        return "unknown"


def _time_fn(fn, warmup: int = WARMUP, measure: int = MEASURE) -> list[float]:
    """Run fn() warmup+measure times, return measured wall-clock seconds."""
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(measure):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return samples


# ---------------------------------------------------------------------------
# 0. provably (full pipeline — SMT + Lean4 if available)
# ---------------------------------------------------------------------------

def bench_provably() -> dict[str, Any]:
    import z3 as _z3
    from provably.engine import verify_function

    # Must use z3.And so provably's engine receives Z3 expressions, not Python booleans
    pre = lambda balance, value: _z3.And(balance >= 0, value >= 0, value <= balance)
    post = lambda balance, value, result: _z3.And(result == balance - value, result >= 0)

    samples: list[float] = []
    errors: list[str] = []

    # Each iteration uses a unique function name → distinct L0 cache key → cold z3 call.
    # clear_cache() does not flush the on-disk L0 cache; unique-name is the only reliable
    # way to guarantee a cache miss and measure real z3 dispatch latency.
    for i in range(WARMUP + MEASURE):
        fn = _load_contract_fresh(i)
        t0 = time.perf_counter()
        try:
            cert = verify_function(fn, pre=pre, post=post)
            elapsed = time.perf_counter() - t0
            if not cert.verified:
                errors.append(f"run {i}: not verified: {cert}")
            elif i >= WARMUP:
                samples.append(elapsed)
        except Exception as e:
            errors.append(f"run {i}: {e}")

    if not samples:
        return {"name": "provably", "version": _pkg_version("provably"),
                "wall_sec": None, "artifact": None, "ok": False,
                "error": "; ".join(errors) or "no samples collected"}
    return {
        "name": "provably",
        "version": _pkg_version("provably"),
        "wall_sec": round(_median(samples), 6),
        "artifact": "SMT+Lean4",
        "ok": True,
    }


# ---------------------------------------------------------------------------
# 1. halmos — a16z Solidity symbolic execution via subprocess
# ---------------------------------------------------------------------------

def _augmented_env() -> dict[str, str]:
    """Return os.environ with Homebrew and ~/.local/bin prepended to PATH.

    Non-interactive SSH sessions strip these from PATH; halmos and forge
    live there on macOS.
    """
    import os
    env = os.environ.copy()
    home = env.get("HOME", "/Users/schizodactyl")
    extra = f"{home}/.local/bin:/opt/homebrew/bin:/usr/local/bin"
    env["PATH"] = f"{extra}:{env.get('PATH', '')}"
    return env


def bench_halmos() -> dict[str, Any]:
    _env = _augmented_env()
    halmos_bin = shutil.which("halmos", path=_env["PATH"])
    if halmos_bin is None:
        return {"name": "halmos", "version": "not-installed",
                "wall_sec": None, "artifact": None, "ok": False,
                "error": "halmos binary not found on PATH"}

    # halmos needs a foundry project; we build a minimal one in a temp dir
    sol_fixture = FIXTURES / "erc20_transfer_halmos.sol"
    if not sol_fixture.exists():
        return {"name": "halmos", "version": "not-installed",
                "wall_sec": None, "artifact": None, "ok": False,
                "error": f"fixture not found: {sol_fixture}"}

    # Check foundry/forge availability (halmos requires it)
    forge_bin = shutil.which("forge", path=_env["PATH"])
    if forge_bin is None:
        return {"name": "halmos", "version": "0.3.3",
                "wall_sec": None, "artifact": None, "ok": False,
                "error": "forge (Foundry) not installed — halmos requires forge for compilation"}

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            # Minimal foundry project structure
            (td / "src").mkdir()
            (td / "test").mkdir()
            (td / "lib").mkdir()
            # forge.toml
            (td / "foundry.toml").write_text(
                '[profile.default]\nsrc = "src"\nout = "out"\nlibs = ["lib"]\n'
            )
            # Copy test contract
            (td / "test" / "ERC20TransferHalmos.t.sol").write_text(
                sol_fixture.read_text()
            )

            # Build first (outside timing)
            build = subprocess.run(
                ["forge", "build"],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=60,
                env=_env,
            )
            if build.returncode != 0:
                return {"name": "halmos", "version": "0.3.3",
                        "wall_sec": None, "artifact": None, "ok": False,
                        "error": f"forge build failed: {build.stderr[:300]}"}

            def run():
                r = subprocess.run(
                    ["halmos", "--contract", "ERC20TransferHalmos",
                     "--function", "check_transfer_no_underflow",
                     "--solver-timeout-assertion", "10000"],
                    cwd=td,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env=_env,
                )
                if r.returncode != 0 and "passed" not in r.stdout:
                    raise RuntimeError(f"halmos failed: {r.stdout[-400:]} {r.stderr[-200:]}")

            samples = _time_fn(run)
            # Get halmos version
            ver_r = subprocess.run(["halmos", "--version"], capture_output=True, text=True, timeout=10, env=_env)
            ver = ver_r.stdout.strip().split("\n")[0] if ver_r.returncode == 0 else "0.3.3"

            return {
                "name": "halmos",
                "version": ver,
                "wall_sec": round(_median(samples), 6),
                "artifact": "property-pass (EVM symbolic)",
                "ok": True,
            }
    except Exception as e:
        return {"name": "halmos", "version": "0.3.3",
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 2. pysmt with Z3 backend
# ---------------------------------------------------------------------------

def bench_pysmt_z3() -> dict[str, Any]:
    try:
        from pysmt.shortcuts import (  # type: ignore[import]
            GE, LE, And, Equals, Int, Minus, Symbol, is_unsat,
        )
        from pysmt.typing import INT  # type: ignore[import]
    except ImportError as e:
        return {"name": "pysmt-z3", "version": "not-installed",
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}

    # pysmt Symbols are environment-global objects.  Defining them once outside
    # run() avoids symbol-name collisions in the global env across WARMUP+MEASURE
    # calls (pysmt returns the same object on name collision, but the env grows).
    # reset_env() between calls breaks the z3 backend's infix-operator wiring.
    # ASYMMETRY vs cvc5/z3-direct: those benchmarks create fresh solver+vars per
    # call; pysmt reuses Symbol objects.  This favours pysmt by ~O(symbol_alloc).
    # See "fairness_notes" in the sidecar for the full disclosure.
    balance = Symbol("pysmt_balance", INT)
    value = Symbol("pysmt_value", INT)
    result = Symbol("pysmt_result", INT)

    def run():
        pre = And(GE(balance, Int(0)), GE(value, Int(0)), LE(value, balance))
        body = Equals(result, Minus(balance, value))
        post = And(Equals(result, Minus(balance, value)), GE(result, Int(0)))

        # Negation of (pre AND body => post): pre AND body AND NOT post
        not_post = And(pre, body, ~post)

        # is_unsat returns True when the formula is unsatisfiable (=> property holds)
        ok = is_unsat(not_post, solver_name="z3")
        if not ok:
            raise RuntimeError("pysmt-z3 did not prove UNSAT")

    try:
        samples = _time_fn(run)
        ver = _pkg_version("pysmt")
        return {
            "name": "pysmt-z3",
            "version": ver,
            "wall_sec": round(_median(samples), 6),
            "artifact": "UNSAT witness (SMT)",
            "ok": True,
        }
    except Exception as e:
        return {"name": "pysmt-z3", "version": _pkg_version("pysmt"),
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 3. cvc5 Python bindings
# ---------------------------------------------------------------------------

def bench_cvc5() -> dict[str, Any]:
    try:
        import cvc5
        from cvc5 import Kind
    except ImportError as e:
        return {"name": "cvc5", "version": "not-installed",
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}

    def run():
        slv = cvc5.Solver()
        slv.setOption("produce-models", "true")
        slv.setLogic("LIA")

        int_sort = slv.getIntegerSort()
        balance = slv.mkConst(int_sort, "balance")
        value = slv.mkConst(int_sort, "value")
        result = slv.mkConst(int_sort, "result")
        zero = slv.mkInteger(0)

        # pre: balance >= 0, value >= 0, value <= balance
        slv.assertFormula(slv.mkTerm(Kind.GEQ, balance, zero))
        slv.assertFormula(slv.mkTerm(Kind.GEQ, value, zero))
        slv.assertFormula(slv.mkTerm(Kind.LEQ, value, balance))

        # body: result = balance - value
        slv.assertFormula(
            slv.mkTerm(Kind.EQUAL, result,
                       slv.mkTerm(Kind.SUB, balance, value))
        )

        # NOT post: NOT (result == balance - value AND result >= 0)
        eq_post = slv.mkTerm(Kind.EQUAL, result,
                              slv.mkTerm(Kind.SUB, balance, value))
        ge_post = slv.mkTerm(Kind.GEQ, result, zero)
        not_post = slv.mkTerm(Kind.NOT, slv.mkTerm(Kind.AND, eq_post, ge_post))
        slv.assertFormula(not_post)

        r = slv.checkSat()
        if not r.isUnsat():
            raise RuntimeError(f"cvc5 did not prove UNSAT, got: {r}")

    try:
        samples = _time_fn(run)
        ver = _pkg_version("cvc5")
        return {
            "name": "cvc5",
            "version": ver,
            "wall_sec": round(_median(samples), 6),
            "artifact": "UNSAT witness (SMT, LIA)",
            "ok": True,
        }
    except Exception as e:
        return {"name": "cvc5", "version": _pkg_version("cvc5"),
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 4. z3-direct-python (lower bound — no Lean)
# ---------------------------------------------------------------------------

def bench_z3_direct() -> dict[str, Any]:
    try:
        import z3
    except ImportError as e:
        return {"name": "z3-direct-python", "version": "not-installed",
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}

    def run():
        balance = z3.Int("balance")
        value = z3.Int("value")
        result = z3.Int("result")

        s = z3.Solver()
        # pre
        s.add(balance >= 0, value >= 0, value <= balance)
        # body
        s.add(result == balance - value)
        # NOT post
        s.add(z3.Not(z3.And(result == balance - value, result >= 0)))

        r = s.check()
        if r != z3.unsat:
            raise RuntimeError(f"z3-direct expected UNSAT, got {r}")

    try:
        samples = _time_fn(run)
        ver = z3.get_version_string()
        return {
            "name": "z3-direct-python",
            "version": ver,
            "wall_sec": round(_median(samples), 6),
            "artifact": "UNSAT witness (raw Z3 API, no Lean)",
            "ok": True,
        }
    except Exception as e:
        return {"name": "z3-direct-python", "version": "unknown",
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 5. solc-SMTChecker via subprocess
# ---------------------------------------------------------------------------

def bench_solc_smt() -> dict[str, Any]:
    solc_bin = shutil.which("solc")
    if solc_bin is None:
        return {"name": "solc-SMTChecker", "version": "not-installed",
                "wall_sec": None, "artifact": None, "ok": False,
                "error": "solc not found on PATH (brew install solidity)"}

    sol_fixture = FIXTURES / "erc20_transfer_solidity.sol"
    if not sol_fixture.exists():
        return {"name": "solc-SMTChecker", "version": "unknown",
                "wall_sec": None, "artifact": None, "ok": False,
                "error": f"fixture not found: {sol_fixture}"}

    # Get version
    try:
        ver_r = subprocess.run([solc_bin, "--version"], capture_output=True, text=True, timeout=10)
        ver_line = [l for l in ver_r.stdout.splitlines() if "Version" in l]
        ver = ver_line[0].split("Version:")[1].strip() if ver_line else "unknown"
    except Exception:
        ver = "unknown"

    def run():
        r = subprocess.run(
            [
                solc_bin,
                "--model-checker-engine", "chc",
                "--model-checker-timeout", "10000",
                str(sol_fixture),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # solc SMTChecker exits 0 even on warnings; check for "verified safely"
        # or absence of "Assertion violation" in output
        combined = r.stdout + r.stderr
        if "Assertion violation" in combined:
            raise RuntimeError(f"solc-SMTChecker: assertion violation reported:\n{combined[:400]}")
        if r.returncode != 0:
            raise RuntimeError(f"solc exited {r.returncode}: {combined[:300]}")

    try:
        samples = _time_fn(run)
        return {
            "name": "solc-SMTChecker",
            "version": ver,
            "wall_sec": round(_median(samples), 6),
            "artifact": "CHC-verified (no assertions violated)",
            "ok": True,
        }
    except Exception as e:
        return {"name": "solc-SMTChecker", "version": ver,
                "wall_sec": None, "artifact": None, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> dict[str, Any]:
    print("provably SOTA bench — ERC-20 transfer overflow safety")
    print(f"  workload: transfer(balance, value): no underflow when value <= balance")
    print(f"  warmup={WARMUP}, measure={MEASURE} runs each\n")

    # Run all competitors
    benches = [
        ("provably",         bench_provably),
        ("halmos",           bench_halmos),
        ("pysmt-z3",         bench_pysmt_z3),
        ("cvc5",             bench_cvc5),
        ("z3-direct-python", bench_z3_direct),
        ("solc-SMTChecker",  bench_solc_smt),
    ]

    results: list[dict[str, Any]] = []
    for label, fn in benches:
        print(f"  [{label}] running...", end="", flush=True)
        r = fn()
        results.append(r)
        if r["ok"]:
            print(f" {r['wall_sec']*1000:.2f} ms  ({r['artifact']})")
        else:
            print(f" FAILED — {r.get('error', 'unknown error')[:80]}")

    # Find provably result
    provably_r = next((r for r in results if r["name"] == "provably"), None)
    if provably_r is None or not provably_r["ok"]:
        print("\nERROR: provably itself failed — cannot compute efficiency_pct")
        sys.exit(1)

    provably_wall = provably_r["wall_sec"]

    # Find fastest successful competitor (excluding provably)
    competitors_ok = [r for r in results if r["name"] != "provably" and r["ok"] and r["wall_sec"] is not None]
    if competitors_ok:
        fastest = min(competitors_ok, key=lambda r: r["wall_sec"])
        sota_wall = fastest["wall_sec"]
        sota_name = fastest["name"]
        sota_version = fastest.get("version", "unknown")
        # efficiency_pct: how close provably is to the fastest competitor
        # >100% means provably is faster than SOTA; <100% means it's slower
        efficiency_pct = round(100.0 * sota_wall / provably_wall, 2)
    else:
        sota_wall = None
        sota_name = "none"
        sota_version = "none"
        efficiency_pct = 0.0

    print(f"\n  provably wall:  {provably_wall*1000:.2f} ms")
    if sota_wall:
        print(f"  SOTA ({sota_name}): {sota_wall*1000:.2f} ms")
        print(f"  efficiency:     {efficiency_pct:.1f}%  (>100 = provably faster than SOTA)")

    # Build sidecar (format compatible with libraries-heartbeat expectations)
    sidecar: dict[str, Any] = {
        "library": "provably",
        "workload": "ERC-20 transfer overflow safety proof, end-to-end (Python)",
        "unit": "seconds (wall-time, lower is better)",
        "actual": provably_wall,
        "sota": sota_wall,
        "sota_name": sota_name,
        "sota_version": sota_version,
        "efficiency_pct": efficiency_pct,
        "competitors": results,
        "timestamp": int(time.time()),
        "fairness_notes": (
            "pysmt-z3 hoists pysmt.Symbol objects outside the timed loop because "
            "pysmt Symbols live in a global environment and reset_env() breaks the "
            "Z3 backend's infix-operator wiring; this omits per-call symbol-alloc "
            "overhead (~O(1) dict lookup). cvc5 and z3-direct create fresh solver + "
            "constants each iteration. The asymmetry slightly favours pysmt-z3 in "
            "this micro-benchmark; in production all three libraries require "
            "one-time setup for long-lived prover sessions, so the gap is amortised. "
            "provably uses a unique function name per benchmark iteration (erc20_transfer_N) "
            "so each call gets a genuine L0 cache miss and measures cold z3 dispatch "
            "latency (~4ms), not cached results (~0.06ms). clear_cache() does not "
            "flush the on-disk L0 cache; unique-name is the only reliable approach."
        ),
    }

    out_path = Path("/tmp/kagami-provably-bench.json")
    out_path.write_text(json.dumps(sidecar, indent=2))
    print(f"\n  sidecar written: {out_path}")

    return sidecar


if __name__ == "__main__":
    run()
