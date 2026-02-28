# The Strange Loop

provably proves its own internal functions using its own `@verified` decorator.
The tool that verifies code is verified by the tool.

---

## What is self-verified

Every function in `src/provably/_self_proof.py` carries a `ProofCertificate` at import time.

| Function | Precondition | Postcondition |
|----------|-------------|---------------|
| `_z3_min(a, b)` | -- | `result <= a`, `result <= b`, `result == a \| result == b` |
| `_z3_max(a, b)` | -- | `result >= a`, `result >= b`, `result == a \| result == b` |
| `_z3_abs(x)` | -- | `result >= 0`, `result == x \| result == -x` |
| `clamp(val, lo, hi)` | `lo <= hi` | `lo <= result <= hi`; in-range passthrough |
| `relu(x)` | -- | `result >= 0`, `result == x \| result == 0` |
| `bounded_increment(x)` | `0 <= x <= 99` | `result == x + 1` |
| `safe_divide(a, b)` | `b > 0` | `result * b <= a < result * b + b` |
| `identity(x)` | -- | `result == x` |
| `negate_negate(x)` | -- | `result == x` |
| `max_of_abs(a, b)` | -- | `result >= 0`, result is one of `a, -a, b, -b` |

All ten: <span class="proof-qed proof-qed--glow">Q.E.D.</span>
If any degrades to `COUNTEREXAMPLE` or `UNKNOWN`, CI fails.

---

## How it works

The self-proof module uses the same pipeline as user code:

```python title="src/provably/_self_proof.py (excerpt)"
from provably.decorators import verified

@verified(
    post=lambda a, b, result: (result <= a) & (result <= b) & ((result == a) | (result == b)),
)
def _z3_min(a: float, b: float) -> float:
    if a <= b:
        return a
    else:
        return b

_z3_min.__proof__.verified   # True
str(_z3_min.__proof__)       # "[Q.E.D.] _z3_min"
```

!!! proof "Why selectivity matters"
    The weak postcondition `(result <= a) & (result <= b)` is satisfied by
    `result = -inf`. The stronger form adds `(result == a) | (result == b)`,
    ruling out any value that isn't one of the inputs.

---

## Reading a certificate

```python
from provably._self_proof import clamp

cert = clamp.__proof__
cert.status         # Status.VERIFIED
cert.verified       # True
cert.solver_time_ms # 3.4
cert.z3_version     # "4.13.0"
str(cert)           # "[Q.E.D.] clamp"
```

---

## The trusted computing base

Every formal proof has a TCB -- components whose correctness is assumed:

1. **Python's AST parser** -- source must match what the runtime executes.
2. **provably's translator** (~500 LOC) -- must faithfully map Python to Z3 semantics. Primary failure mode.
3. **Z3** -- must correctly implement the SMT decision procedure.
4. **CPython** -- the interpreter running everything.

Self-proofs reduce the translator's blast radius: if `_z3_min` fails at runtime,
either the translator has a bug or Z3 does. Either way, the self-proof catches it.

What self-proofs **cannot** guarantee: correct translation of constructs not exercised
in `_self_proof.py`. Unknown constructs that trigger `TranslationError` are `SKIPPED`.

---

## CI integration

```yaml title=".github/workflows/ci.yml"
self-proof:
  name: Self-proof
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
      with: { enable-cache: true }
    - run: uv sync --group dev
    - name: provably proves itself
      run: uv run pytest tests/test_self_proof.py -v
```

The test asserts all 10 functions have `status == VERIFIED`. No grace period.

---

## Why it matters

- Exercises real branching, integer arithmetic, and multi-argument preconditions -- the core supported subset.
- Regression safety net: any translator change that breaks a self-proof is caught before merge.
- Concrete demonstration of what `VERIFIED` means.

The strange loop is load-bearing.
