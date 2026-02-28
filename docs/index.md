# provably

**Proof-carrying Python — Z3-backed formal verification via decorators and refinement types**

---

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

assert integer_sqrt.__proof__.verified  # Q.E.D.
```

</div>

provably translates Python functions into Z3 constraints and checks them with an SMT
solver. A `verified=True` result is a **mathematical proof** — not a test, not a sample,
not an approximation. It means the contract holds for **every possible input** satisfying
the precondition, simultaneously and unconditionally.

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

```bash
pip install provably[z3]
```

The `[z3]` extra installs `z3-solver`. The base package has zero dependencies — `@runtime_checked` works without Z3.

## Features

<div class="feature-grid">

<div class="feature-card">

### `@verified` decorator

State pre/post contracts as Python lambdas. provably proves them at import time using
Z3. Zero overhead at call sites — the proof happens once, at decoration.

```python
@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b
# modulo.__proof__.verified → True  [Q.E.D.]
```

</div>

<div class="feature-card">

### Refinement types

Embed constraints directly in `typing.Annotated` signatures. No separate `pre=` lambda
needed for parameter bounds.

```python
from typing import Annotated
from provably.types import Between, Gt

@verified(post=lambda x, result: result >= x)
def double(x: Annotated[float, Gt(0)]) -> float:
    return x * 2
# x > 0 becomes a Z3 precondition automatically
```

</div>

<div class="feature-card">

### Counterexample extraction

When a proof fails, Z3 produces the exact input that breaks the contract. Not a fuzzer
guess — a mathematically guaranteed witness.

```python
@verified(post=lambda n, result: result * result == n)
def bad_sqrt(n: int) -> int:
    return n // 2  # wrong

cert = bad_sqrt.__proof__
cert.counterexample  # {'n': 2, '__return__': 1}
# 1 * 1 = 1 ≠ 2. Q.E.D. it's wrong.
```

</div>

<div class="feature-card">

### Compositionality

Call verified helpers from verified functions. provably reuses their contracts
without re-examining their bodies — classical assume/guarantee reasoning.

```python
@verified(
    contracts={"abs_val": abs_val.__contract__},
    post=lambda x, result: result >= 0,
)
def distance(x: float) -> float:
    return abs_val(x)
# abs_val's postcondition is an assumption here
```

</div>

<div class="feature-card">

### `@runtime_checked`

Assert contracts at every call without Z3. Ideal for production guards, unsupported
constructs, or environments without `z3-solver` installed.

```python
@runtime_checked(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
)
def safe_sqrt(x: float) -> float:
    return x ** 0.5

safe_sqrt(-1.0)  # raises ContractViolationError
```

</div>

<div class="feature-card">

### Self-proving

<span class="proof-qed proof-qed--glow">Q.E.D.</span>&nbsp; provably uses `@verified` to prove its own
internal functions on every CI push. If the tool can't prove `min`, `max`, `abs`,
and `clamp` correct, something is deeply wrong.

Ten self-proofs. All `VERIFIED`. The [strange loop](self-proof.md) is load-bearing.

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
| [Soundness](concepts/soundness.md) | What "proven" means, epistemological boundaries |
| [Supported Python](guides/supported-python.md) | Supported and unsupported constructs |
| [Pytest integration](guides/pytest.md) | CI assertions, `verify_module()` in tests |
| [Errors and debugging](guides/errors.md) | Reading counterexamples, `TranslationError` fixes |
| [API: decorators](api/decorators.md) | `@verified`, `@runtime_checked`, `verify_module`, `configure` |
| [API: types](api/types.md) | Refinement markers, `extract_refinements`, convenience aliases |
| [API: engine](api/engine.md) | `ProofCertificate`, `Status`, `verify_function`, `clear_cache` |
| [Self-proof](self-proof.md) | The strange loop — provably proves itself |
