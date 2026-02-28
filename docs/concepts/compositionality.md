# Compositionality

Build large proofs from small pieces. provably reuses verified contracts without
re-examining function bodies -- classical assume/guarantee reasoning.

## The pattern

```python
from provably import verified

@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)),
)
def my_abs(x: float) -> float:
    return x if x >= 0.0 else -x
# my_abs.__proof__.verified -> True

@verified(
    contracts={"my_abs": my_abs.__contract__},
    post=lambda x, y, result: result >= 0,
)
def manhattan(x: float, y: float) -> float:
    return my_abs(x) + my_abs(y)
# manhattan.__proof__.verified -> True
# provably never examined my_abs's body -- only its postcondition.
```

Without `contracts=`, the translator raises `TranslationError` on the `my_abs(...)` call.
With it, provably substitutes a fresh Z3 variable constrained by the callee's postcondition.

## Modular verification

$$\frac{P_1 \Rightarrow Q_1 \quad P_2 \land Q_1(x_1) \Rightarrow Q_2}{P_1 \land P_2 \Rightarrow Q_2}$$

The two proofs are independent. Changing `my_abs`'s body invalidates `my_abs.__proof__`
but not `manhattan.__proof__` until re-verification.

## `__contract__`

Every `@verified` function exposes `__contract__`:

```python
my_abs.__contract__
# {'pre': None, 'post': <lambda>, 'verified': True}
```

The key in `contracts=` must match the function name used in the body.

## Multiple contracts

```python
@verified(
    contracts={
        "clamp": clamp.__contract__,
        "my_abs": my_abs.__contract__,
    },
    pre=lambda lo, hi, x: lo <= hi,
    post=lambda lo, hi, x, result: (result >= 0) & (result <= hi),
)
def clamped_abs(lo: float, hi: float, x: float) -> float:
    return clamp(my_abs(x), lo, hi)
# clamped_abs.__proof__.verified -> True
```

## Unverified callees

Calling a function not in `contracts=` and not a builtin (`min`, `max`, `abs`)
raises `TranslationError`. This is intentional -- silently ignoring calls would
produce unsound proofs.

## Re-verification

If you change a helper's implementation, its proof is recomputed on import.
Use `verify_module()` in tests to catch stale callers:

```python
from provably.engine import verify_module
import mypackage.math_utils as m

def test_all_proofs_hold():
    results = verify_module(m)
    failures = {name: cert for name, cert in results.items() if not cert.verified}
    assert not failures, f"Proof failures: {failures}"
```
