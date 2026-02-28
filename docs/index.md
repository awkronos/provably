# provably

**Proof-carrying Python — Z3-backed formal verification via decorators and refinement types**

<div class="hero-badges">
  <span class="hero-badge hero-badge--self-proving">&#10003; Self-proving</span>
  <span class="hero-badge">Zero call-site overhead</span>
  <span class="hero-badge">Mathematical proofs, not tests</span>
  <span class="hero-badge">Counterexample extraction</span>
</div>

<div class="hero-example">

```python
from provably import verified

@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: (result * result <= x) & (x < (result + 1) * (result + 1)),
)
def integer_sqrt(x: int) -> int:
    n = 0
    while (n + 1) * (n + 1) <= x:
        n += 1
    return n

integer_sqrt.__proof__.verified   # True
str(integer_sqrt.__proof__)       # "[Q.E.D.] integer_sqrt"
integer_sqrt.__proof__.status     # Status.VERIFIED
```

</div>

provably translates Python functions into Z3 constraints and checks them with an SMT solver.
A `verified=True` result is a **mathematical proof** — not a test, not a sample, not a fuzzer guess.
It means the contract holds for **every possible input** satisfying the precondition, simultaneously
and unconditionally.

**The pipeline:**

<div class="proof-flow">
  <span class="proof-flow-step">Python source</span>
  <span class="proof-flow-arrow">→</span>
  <span class="proof-flow-step">AST parse</span>
  <span class="proof-flow-arrow">→</span>
  <span class="proof-flow-step">Z3 constraints</span>
  <span class="proof-flow-arrow">→</span>
  <span class="proof-flow-step">SMT query ¬post</span>
  <span class="proof-flow-arrow">→</span>
  <span class="proof-flow-step proof-flow-step--final">UNSAT → Q.E.D.</span>
</div>

## Install

=== "pip"

    ```bash
    pip install provably[z3]
    ```

=== "uv"

    ```bash
    uv add "provably[z3]"
    ```

The `[z3]` extra installs `z3-solver`. The base package has zero dependencies —
`@runtime_checked` works without Z3.

## What makes provably different

<div class="feature-grid">

<div class="feature-card">

### Proof certificates, not test results

Z3 returns `UNSAT` — no counterexample exists. The result is attached to `func.__proof__`
as a frozen `ProofCertificate`. One proof per function, computed at import time, zero
overhead at every call site.

```python
cert = my_func.__proof__
cert.verified       # True
cert.status         # Status.VERIFIED
cert.solver_time_ms # 2.4
cert.z3_version     # "4.13.0"
```

</div>

<div class="feature-card">

### Counterexample extraction

When a contract fails, Z3 produces the exact witness — the smallest input that breaks
your specification. Not a fuzzer guess. A mathematically guaranteed counterexample.

```python
@verified(post=lambda n, result: result * result == n)
def bad_sqrt(n: int) -> int:
    return n // 2

bad_sqrt.__proof__.counterexample
# {'n': 2, '__return__': 1}
# 1 * 1 = 1 ≠ 2. Q.E.D. it's wrong.
```

</div>

<div class="feature-card">

### Refinement types

Embed constraints directly in `typing.Annotated` signatures. Parameter bounds become
Z3 preconditions automatically — no separate `pre=` lambda needed.

```python
from provably.types import Between, Gt, NonNegative

@verified(post=lambda p, result: result >= 0)
def scale(
    p: Annotated[float, Between(0, 1)],
    x: Annotated[float, Gt(0)],
) -> NonNegative:
    return p * x
```

</div>

<div class="feature-card">

### Compositionality

Call verified helpers from verified functions. provably reuses their contracts without
re-examining their bodies — classical assume/guarantee reasoning. Build large proofs from
small pieces.

```python
@verified(
    contracts={"abs_val": abs_val.__contract__},
    post=lambda x, y, result: result >= 0,
)
def manhattan(x: float, y: float) -> float:
    return abs_val(x) + abs_val(y)
```

</div>

<div class="feature-card">

### `@runtime_checked`

Assert contracts at every call without Z3. Ideal for production guards, unsupported
constructs, or environments without `z3-solver` installed. Raises `ContractViolationError`
on any violation.

```python
@runtime_checked(
    pre=lambda x: x >= 0,
    post=lambda x, result: abs(result * result - x) < 1e-9,
)
def precise_sqrt(x: float) -> float:
    return x ** 0.5

precise_sqrt(-1.0)  # raises ContractViolationError
```

</div>

<div class="feature-card">

### Self-proving

<span class="proof-qed proof-qed--glow">Q.E.D.</span>&nbsp; provably uses `@verified` to prove its own internal
functions on every CI push. Ten self-proofs, all `VERIFIED`. If the tool can't prove
`min`, `max`, `abs`, `clamp`, and `relu` correct, the build breaks.

The strange loop is load-bearing — see [Self-Proof](self-proof.md).

</div>

</div>

## Documentation

| | |
|---|---|
| [Getting started](getting-started.md) | Install, first proof, what Q.E.D. means |
| [How it works](concepts/how-it-works.md) | AST translation, Z3 queries, the TCB |
| [Refinement types](concepts/refinement-types.md) | `Annotated` markers, convenience aliases |
| [Contracts](concepts/contracts.md) | Pre/post lambda syntax, `&`/`\|` vs `and`/`or` |
| [Compositionality](concepts/compositionality.md) | Modular verification, proof dependencies |
| [Soundness](concepts/soundness.md) | What "proven" means, epistemological limits |
| [Supported Python](guides/supported-python.md) | Supported and unsupported constructs |
| [Pytest integration](guides/pytest.md) | CI assertions, `verify_module()` in tests |
| [Errors and debugging](guides/errors.md) | Reading counterexamples, `TranslationError` fixes |
| [Self-proof](self-proof.md) | The strange loop — provably proves itself |
