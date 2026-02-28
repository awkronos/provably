# Compositionality

One of the fundamental properties of formal verification is **compositionality**: a larger
proof can be built by combining smaller proofs, without re-checking the internals of each
component.

provably supports this via the `contracts=` parameter.

## The idea

Suppose you have a verified helper:

```python
from provably import verified

@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)),
)
def my_abs(x: float) -> float:
    return x if x >= 0.0 else -x

# my_abs.__proof__.verified → True
```

Now you want to write a function that calls `my_abs`. Without `contracts=`, the translator
encounters the call `my_abs(...)` and raises `TranslationError` — it cannot inline the
body of `my_abs` into the Z3 query automatically.

With `contracts=`, you tell provably: "Trust the verified contracts of these functions.
When you see a call, substitute the result with a fresh Z3 variable constrained by
the callee's postcondition."

```python
@verified(
    contracts={"my_abs": my_abs.__contract__},
    post=lambda x, y, result: result >= 0,
)
def manhattan(x: float, y: float) -> float:
    return my_abs(x) + my_abs(y)

# manhattan.__proof__.verified → True
# provably never examined my_abs's body — only its postcondition.
```

## Modular verification

This is classical **assume/guarantee** reasoning:

$$\frac{P_1 \Rightarrow Q_1 \quad P_2 \land Q_1(x_1) \Rightarrow Q_2}{P_1 \land P_2 \Rightarrow Q_2}$$

- Verify `my_abs` once (establishes $Q_1$: result is non-negative and equals $x$ or $-x$).
- Verify `manhattan` using $Q_1$ as an assumption (establishes $Q_2$: result is non-negative).
- The two proofs are independent — changing `my_abs`'s body invalidates `my_abs.__proof__`
  but not `manhattan.__proof__` until you re-verify.

## Accessing `__contract__`

Every `@verified` function exposes `__contract__`:

```python
my_abs.__contract__
# {'pre': None, 'post': <lambda>, 'verified': True}
```

Pass this directly to `contracts=` of the calling function:

```python
contracts={"my_abs": my_abs.__contract__}
```

The key must match the function name used in the body (`"my_abs"` in the example above).

## Multiple contracts

Pass a dict with one entry per helper:

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

# clamped_abs.__proof__.verified → True
```

## Unverified callees

If you call a function that is **not** listed in `contracts=` and is not `min`, `max`, or
`abs` (which are handled natively), the translator produces `TranslationError`:

```
TranslationError: Call to 'helper_a' at line 3 is not a supported builtin and
not listed in contracts=. Add it to contracts= or inline the logic.
```

This is intentional. Silently ignoring call sites would produce an unsound proof that
does not account for what the helper actually returns.

## Re-verification

If you change a helper's implementation, its `__proof__` is recomputed on the next import
(proofs are computed at decoration time). Any caller that depended on the old contracts
should be re-verified. Use `verify_module()` in your test suite to catch this automatically:

```python
# tests/test_proofs.py
from provably.engine import verify_module
import mypackage.math_utils as m

def test_all_proofs_hold():
    results = verify_module(m)
    failures = {
        name: cert
        for name, cert in results.items()
        if not cert.verified
    }
    assert not failures, (
        "Proof failures:\n" + "\n".join(
            f"  {name}: {cert}"
            for name, cert in failures.items()
        )
    )
```
