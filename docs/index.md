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

**Proof certificates** — Z3 returns UNSAT. The certificate attaches to `func.__proof__`, computed at import time.

```python
cert = clamp.__proof__
cert.verified        # True
cert.solver_time_ms  # 2.4
cert.to_prompt()     # LLM-ready repair format
```

**Counterexample extraction** — When a contract fails, Z3 returns the exact input that breaks it.

```python
@verified(post=lambda n, r: r * r == n)
def bad(n: int) -> int:
    return n // 2

bad.__proof__.counterexample
# {'n': 2, '__return__': 1}
```

**Refinement types** — Embed bounds in `Annotated` signatures.

```python
@verified(post=lambda p, x, r: r >= 0)
def scale(
    p: Annotated[float, Between(0, 1)],
    x: Annotated[float, Gt(0)],
) -> NonNegative:
    return p * x  # verified
```

**Compositionality** — Reuse verified contracts via `contracts=`.

```python
@verified(
    contracts={"my_abs": my_abs.__contract__},
    post=lambda x, y, r: r >= 0,
)
def manhattan(x: float, y: float) -> float:
    return my_abs(x) + my_abs(y)  # verified
```

**Runtime checking** — `@runtime_checked` asserts contracts at call time without Z3.

**Self-verifying** — provably proves its own `min`, `max`, `abs`, `clamp`, `relu` on every CI push. See [Self-Proof](self-proof.md).

**Hypothesis bridge** — `pip install provably[hypothesis]` for `from_refinements()`, `hypothesis_check()`, and `@proven_property`.

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
