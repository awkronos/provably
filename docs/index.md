# provably

**Z3-backed formal verification for Python — via decorators and refinement types**

<div class="hero-badges">
  <span class="hero-badge hero-badge--self-proving">&#10003; Self-proving</span>
  <span class="hero-badge">Zero solver overhead at call time</span>
  <span class="hero-badge">Counterexample extraction</span>
</div>

<div class="hero-example" markdown>

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

<div class="feature-card" markdown>

### Proof certificates

Z3 returns UNSAT. The proof attaches to
`func.__proof__` at import time.

```python
cert = clamp.__proof__
cert.verified       # True
cert.solver_time_ms # 2.4
```

</div>

<div class="feature-card" markdown>

### Counterexamples

When a contract fails, Z3 returns the
exact input that breaks it.

```python
@verified(post=lambda n, r: r * r == n)
def bad(n: int) -> int:
    return n // 2

bad.__proof__.counterexample
# {'n': 2, '__return__': 1}
```

</div>

<div class="feature-card" markdown>

### Refinement types

Embed bounds directly in type annotations
via `Annotated`.

```python
@verified
def scale(
    p: Annotated[float, Between(0, 1)],
    x: Annotated[float, Gt(0)],
) -> NonNegative:
    return p * x
```

</div>

<div class="feature-card" markdown>

### Compositionality

Reuse verified contracts without
re-examining function bodies.

```python
@verified(
    contracts={"abs": abs.__contract__},
    post=lambda x, y, r: r >= 0,
)
def dist(x: float, y: float) -> float:
    return abs(x) + abs(y)
```

</div>

<div class="feature-card" markdown>

### Runtime checking

`@runtime_checked` asserts contracts at
call time. No Z3 required.

```python
@runtime_checked(
    pre=lambda x: x >= 0,
    post=lambda x, r: r * r <= x + 1,
)
def isqrt(x: int) -> int:
    ...
```

</div>

<div class="feature-card" markdown>

### Self-verifying

provably proves its own `min`, `max`, `abs`,
`clamp`, `relu` on every CI push. If it can't
prove its own builtins, the build breaks.

[Self-Proof &rarr;](self-proof.md)

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
| [Self-proof](self-proof.md) | provably verifies its own functions |
