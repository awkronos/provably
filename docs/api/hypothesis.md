# provably.hypothesis

Bridge between provably's Z3 verification and
[Hypothesis](https://hypothesis.works/) property-based testing.

```bash
pip install provably[hypothesis]
```

```python
from provably.hypothesis import (
    from_refinements,
    from_counterexample,
    hypothesis_check,
    proven_property,
    HypothesisResult,
)
```

All `hypothesis` imports are lazy, so this module is importable even when
Hypothesis is not installed. Calling a function that needs Hypothesis without
it installed raises `ImportError` with an install hint.

When to reach for this module:

- **Z3 returned `UNKNOWN`** (e.g. nonlinear arithmetic the solver could not
  decide). `hypothesis_check` / `proven_property` give you property-test
  evidence as a fallback.
- **You want generators that respect refinement types.** `from_refinements`
  turns `Annotated[int, Between(0, 10)]` into a matching Hypothesis strategy.
- **You found a counterexample with Z3** and want to reproduce it as a
  concrete failing input via `from_counterexample`.

---

## `from_refinements(typ)`

Build a Hypothesis strategy from an `Annotated` refinement type. Honors
`Gt`, `Ge`, `Lt`, `Le`, `Between`, and `NotEq` markers on `int` / `float`
bases.

```python
from typing import Annotated
from provably.types import Between
from provably.hypothesis import from_refinements

strat = from_refinements(Annotated[int, Between(0, 10)])
strat.example()  # an int in [0, 10]
```

---

## `from_counterexample(cert)`

Extract the input-argument dict from a `ProofCertificate` whose status is
`COUNTEREXAMPLE` (the `__return__` key is removed). Raises `ValueError` if the
certificate has no counterexample.

```python
ce = from_counterexample(bad_func.__proof__)
# {'x': -1}  — feed straight back into bad_func(**ce)
```

---

## `hypothesis_check(func, pre=None, post=None, max_examples=1000)`

Run Hypothesis property testing directly. Strategies come from the function's
type annotations via `from_refinements`; `pre` is applied as an `assume()`
filter and `post` is checked on each example.

Returns a [`HypothesisResult`](#hypothesisresult).

```python
from provably.hypothesis import hypothesis_check

result = hypothesis_check(
    sqrt_approx,
    pre=lambda x: x >= 0,
    post=lambda x, r: r >= 0,
    max_examples=500,
)
result.passed         # True / False
result.counterexample # falsifying input dict, or None
result.examples_run   # how many examples ran
```

---

## `proven_property(func=None, *, pre=None, post=None, max_examples=1000)`

Decorator that tries Z3 first and falls back to Hypothesis **only** when Z3
returns `UNKNOWN`. Attaches:

- `__proof__` — the `ProofCertificate` from Z3.
- `__hypothesis_result__` — a `HypothesisResult`, or `None` when Z3 decided the
  goal (verified or counterexample) and no fallback was needed.

Like `@verified`, it adds **no runtime overhead** — the wrapped function just
calls the original.

```python
from provably.hypothesis import proven_property

@proven_property(pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
def half(x: float) -> float:
    return x / 2

half.__proof__.verified           # True — Z3 decided it
half.__hypothesis_result__        # None (no fallback was needed)
```

The fallback only fires when Z3 returns `Status.UNKNOWN`. When Z3 verifies the
goal, finds a counterexample, or hits a `TRANSLATION_ERROR`,
`__hypothesis_result__` stays `None`.

---

## `HypothesisResult`

Dataclass returned by `hypothesis_check`.

| Field | Type | Meaning |
|---|---|---|
| `passed` | `bool` | `True` if no falsifying example was found |
| `counterexample` | `dict \| None` | Falsifying input args, or `None` |
| `examples_run` | `int` | Number of examples Hypothesis executed |

---

::: provably.hypothesis
