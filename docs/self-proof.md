# The Strange Loop

provably proves its own internal functions. This page explains what that means,
why it matters, and what the epistemological limits are.

---

## The concept

Douglas Hofstadter called it a *strange loop*: a system that, in traversing its
levels, finds itself back at its own starting point. Gödel's incompleteness
theorems are the canonical example — a formal system constructing a sentence
that says, of itself, *I am not provable within this system.*

provably occupies a different position. It does not claim to prove its own
*completeness* — that would require a meta-system, and so on forever. What it
does is narrower and more concrete: it uses its own `@verified` decorator to
prove that its own pure helper functions satisfy their contracts. The translator
runs. Z3 closes the proof. The certificate attaches to the function.

The loop is genuine: **the tool that verifies code is verified by the tool.**

---

## What is self-verified

Every function in `src/provably/_self_proof.py` is decorated with `@verified`
and collects a `ProofCertificate` at import time.

!!! note "Postcondition strength"
    Each postcondition is the **strongest** property Z3 can close for the
    given fragment. Selectivity (result equals one of the inputs), passthrough
    (identity when in range), and exactness (result == x + 1) are all proved
    where possible.

| Function | Precondition | Postcondition |
|----------|-------------|---------------|
| `_z3_min(a, b)` | — | `result <= a`, `result <= b`, and `result == a` or `result == b` |
| `_z3_max(a, b)` | — | `result >= a`, `result >= b`, and `result == a` or `result == b` |
| `_z3_abs(x)` | — | `result >= 0` and `result == x` or `result == -x` |
| `clamp(val, lo, hi)` | `lo <= hi` | `lo <= result <= hi`; when `val` is in range, `result == val` |
| `relu(x)` | — | `result >= 0` and `result == x` or `result == 0` |
| `bounded_increment(x)` | `0 <= x <= 99` | `result == x + 1` (implies `1 <= result <= 100`) |
| `safe_divide(a, b)` | `b > 0` | `result * b <= a < result * b + b` (floor-division bound) |
| `identity(x)` | — | `result == x` |
| `negate_negate(x)` | — | `result == x` |
| `max_of_abs(a, b)` | — | `result >= 0` and `result` is one of `a`, `-a`, `b`, `-b` |

All ten proofs carry status <span class="proof-qed proof-qed--glow">Q.E.D.</span>.
If any proof ever degrades to `COUNTEREXAMPLE` or `UNKNOWN`, CI fails immediately.

---

## How it works

The self-proof module is not special-cased. It is a normal Python module that
imports `@verified` and uses it:

```python title="src/provably/_self_proof.py (excerpt)"
from provably.decorators import verified

@verified(
    post=lambda a, b, result: (result <= a) & (result <= b) & ((result == a) | (result == b)),
)
def _z3_min(a: float, b: float) -> float:
    """min(a, b): result is the actual minimum."""
    if a <= b:
        return a
    else:
        return b

_z3_min.__proof__.verified   # True
str(_z3_min.__proof__)       # "[Q.E.D.] _z3_min"
```

!!! proof "Why selectivity matters"
    The weak postcondition `(result <= a) & (result <= b)` is satisfied by
    `result = -∞`. The stronger form adds `(result == a) | (result == b)`,
    which Z3 must also prove — ruling out any value that isn't one of the
    two inputs. This is the complete characterisation of `min`.

At import time, the `@verified` decorator:

1. Parses the function body into an AST.
2. Translates each Python construct into a Z3 expression (assignments become
   substitutions, branches become `z3.If`, the contract lambda becomes a
   `z3.BoolRef` assertion).
3. Asks Z3 to find any input violating `¬postcondition`. If Z3 returns `unsat`,
   the proof is closed — no such input exists.
4. Attaches the `ProofCertificate` to `func.__proof__`.

The entire pipeline — from Python source to Z3 model to certificate — executes
on the functions it will later be used to verify.

---

## Reading a certificate

```python
from provably._self_proof import clamp

cert = clamp.__proof__
print(cert.status)         # Status.VERIFIED
print(cert.verified)       # True
print(cert.solver_time_ms) # e.g. 3.4
print(cert.z3_version)     # e.g. "4.13.0"
print(cert.postconditions) # ('And(val < lo, Or(val > hi, result == val), ...)',)
print(cert)                # [Q.E.D.] clamp
```

A `VERIFIED` status means Z3 proved the formula
$\forall \text{inputs} : \text{pre}(\text{inputs}) \Rightarrow \text{post}(\text{inputs}, f(\text{inputs}))$
is unsatisfiable when negated. This is not sampling. It is not fuzzing. It is a
mathematical proof over all possible real-number inputs in Z3's model.

---

## The trusted computing base

Every formal proof has a trusted computing base (TCB) — the set of components
whose correctness must be assumed without further proof. provably's TCB is:

1. **Python's AST parser** — the source must match what the runtime executes.
2. **provably's translator** — `translator.py` must faithfully map Python
   semantics to Z3 semantics. This is the largest risk: a mistranslation
   would produce a proof of the wrong formula.
3. **Z3 itself** — z3-solver must correctly implement the SMT decision
   procedure. Z3 is a mature, extensively tested solver, but it is not
   self-proving.
4. **CPython** — the interpreter that executes both the verified and the
   verifying code.

Self-proofs reduce the translator's blast radius: if `_z3_min` is provably
wrong at runtime, either the translator has a bug (the proof was of a wrong
formula) or Z3 has a soundness bug. In either case, the self-proof *catches
the failure*. The CI job `self-proof` enforces this on every push.

What self-proofs cannot guarantee: that the translator handles *all* Python
constructs correctly. Only the subset used in `_self_proof.py` is exercised.
Unknown constructs that trigger `TranslationError` are `SKIPPED`, not proved.

---

## CI integration

The self-proof job is a required status check on every push and pull request:

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

The test suite in `tests/test_self_proof.py` asserts:

- All 10 functions in `SELF_PROOFS` have `status == VERIFIED`.
- Every postcondition uses the strongest provable form (selectivity, exactness, passthrough).
- Every function still computes the correct result at runtime.
- `__proof__` is attached to every function in the collection.

If a translator regression breaks the proof of `clamp`, CI catches it before
merge. If Z3 times out on any self-proof, the status becomes `UNKNOWN` and
CI fails. There is no grace period.

---

## What this means

Self-proof is not a gimmick. It is a meaningful invariant:

- It shows the translator handles real branching programs, integer arithmetic,
  and multi-argument preconditions — the core of the supported subset.
- It gives library users a concrete demonstration of what `VERIFIED` means.
  If `safe_divide` is truly verified, then for all integers `a` and `b > 0`,
  the expression `a // b * b <= a < a // b * b + b` holds in Z3's integer model.
- It provides a regression safety net. Any change to the translator that
  breaks a self-proof is caught immediately, before it can affect user code.

The strange loop is load-bearing.
