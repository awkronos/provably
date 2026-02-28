# provably

**Z3-backed formal verification for Python — via decorators and refinement types**

<div class="hero-badges">
  <span class="hero-badge hero-badge--self-proving">&#10003; Self-proving</span>
  <span class="hero-badge">Zero solver overhead at call time</span>
  <span class="hero-badge">Counterexample extraction</span>
</div>

<div class="hero-example">

```python
from provably import verified

@verified(
    pre=lambda val, lo, hi: lo <= hi,
    post=lambda val, lo, hi, result: (result >= lo) & (result <= hi),
)
def clamp(val: float, lo: float, hi: float) -> float:
    if val < lo:
        return lo
    elif val > hi:
        return hi
    else:
        return val

clamp.__proof__.verified   # True — for ALL inputs where lo <= hi
clamp.__proof__.status     # Status.VERIFIED
str(clamp.__proof__)       # "[Q.E.D.] clamp"
```

</div>

`verified=True` is a **mathematical proof** -- not a test, not a sample.
The contract holds for **every possible input** satisfying the precondition.

<div class="proof-flow">
  <span class="proof-flow-step">Python source</span>
  <span class="proof-flow-arrow">&rarr;</span>
  <span class="proof-flow-step">AST parse</span>
  <span class="proof-flow-arrow">&rarr;</span>
  <span class="proof-flow-step">Z3 constraints</span>
  <span class="proof-flow-arrow">&rarr;</span>
  <span class="proof-flow-step">SMT query &not;post</span>
  <span class="proof-flow-arrow">&rarr;</span>
  <span class="proof-flow-step proof-flow-step--final">UNSAT &rarr; Q.E.D.</span>
</div>

## Install

=== "pip"

    ```bash
    pip install provably
    ```

=== "uv"

    ```bash
    uv add provably
    ```

## What makes provably different

<div class="feature-grid">

<div class="feature-card">

### Proof certificates

Z3 returns `UNSAT` -- no counterexample exists. The certificate attaches to `func.__proof__`,
computed at import time. No solver runs at call time.

```python
cert = my_func.__proof__
cert.verified       # True
cert.status         # Status.VERIFIED
cert.solver_time_ms # 2.4
```

</div>

<div class="feature-card">

### Counterexample extraction

When a contract fails, Z3 produces the exact witness -- the smallest input
that breaks your specification.

```python
@verified(post=lambda n, result: result * result == n)
def bad_sqrt(n: int) -> int:
    return n // 2

bad_sqrt.__proof__.counterexample
# {'n': 2, '__return__': 1}
```

</div>

<div class="feature-card">

### Refinement types

Embed constraints in `typing.Annotated` signatures. Parameter bounds become
Z3 preconditions automatically.

```python
from provably.types import Between, Gt, NonNegative

@verified(post=lambda p, result: result >= 0)
def scale(
    p: Annotated[float, Between(0, 1)],
    x: Annotated[float, Gt(0)],
) -> NonNegative:
    return p * x
# scale.__proof__.verified -> True
```

</div>

<div class="feature-card">

### Compositionality

Reuse verified contracts without re-examining bodies -- classical assume/guarantee reasoning.

```python
@verified(
    contracts={"abs_val": abs_val.__contract__},
    post=lambda x, y, result: result >= 0,
)
def manhattan(x: float, y: float) -> float:
    return abs_val(x) + abs_val(y)
# manhattan.__proof__.verified -> True
```

</div>

<div class="feature-card">

### `@runtime_checked`

Assert contracts at every call without the solver. Raises `ContractViolationError` on violation.

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

<span class="proof-qed proof-qed--glow">Q.E.D.</span>&nbsp; provably proves its own internal
functions on every CI push. If it can't prove `min`, `max`, `abs`, `clamp`, and `relu` correct,
the build breaks. See [Self-Proof](self-proof.md).

</div>

</div>

## Documentation

| | |
|---|---|
| [Getting started](getting-started.md) | Install, first proof, what Q.E.D. means |
| [How it works](concepts/how-it-works.md) | AST translation, Z3 queries, the TCB |
| [Refinement types](concepts/refinement-types.md) | `Annotated` markers, convenience aliases |
| [Contracts](concepts/contracts.md) | Pre/post lambda syntax, `&`/`|` vs `and`/`or` |
| [Compositionality](concepts/compositionality.md) | Modular verification, proof dependencies |
| [Soundness](concepts/soundness.md) | What "proven" means, epistemological limits |
| [Supported Python](guides/supported-python.md) | Supported and unsupported constructs |
| [Pytest integration](guides/pytest.md) | CI assertions, `verify_module()` |
| [Errors and debugging](guides/errors.md) | Counterexamples, `TranslationError` fixes |
| [Self-proof](self-proof.md) | The strange loop -- provably proves itself |
