# provably

**Proof-carrying Python — Z3-backed formal verification via decorators and refinement types**

---

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

provably translates Python functions into Z3 constraints and checks them with an SMT solver.
A `verified=True` result is a **mathematical proof** — not a test, not a sample, not an approximation.
It means the contract holds for every possible input satisfying the precondition.

## Install

```bash
pip install provably[z3]
```

The `[z3]` extra installs `z3-solver`. The base package has zero dependencies.

## Features

- **`@verified` decorator** — state pre/post contracts as Python lambdas; provably proves them.
- **Refinement types** — embed constraints directly in `typing.Annotated` signatures using
  `Ge`, `Le`, `Between`, `Gt`, `Lt`, `NotEq` markers.
- **Counterexample extraction** — when a proof fails, Z3 produces a concrete input that
  violates the contract. `func.__proof__.counterexample` gives you the exact values.
- **Proof certificates** — every verified function carries a `__proof__` attribute with
  `verified`, `solver_time`, `strategy`, and optionally `counterexample`.
- **Compositionality** — call verified helper functions from verified functions and reuse
  their contracts modularly.
- **`@runtime_checked`** — assert contracts at every call without invoking Z3. Ideal for
  production guards or environments without `z3-solver`.
- **`verify_module()`** — batch-verify every `@verified` function in a module. Use in
  test suites to make verification part of CI.
- **Zero mandatory dependencies** — `pip install provably` works without Z3.

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
