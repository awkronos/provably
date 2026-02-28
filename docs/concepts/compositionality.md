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
    pre=lambda x: x >= 0,
    post=lambda x, result: (result >= 0) & (result * result <= x),
)
def isqrt(x: int) -> int:
    n = 0
    while (n + 1) * (n + 1) <= x:
        n += 1
    return n
```

Now you want to write a function that calls `isqrt`. Without `contracts=`, the translator
would encounter the call `isqrt(...)` and raise `TranslationError` — it cannot inline the
entire body of `isqrt` into the Z3 query.

With `contracts=`, you tell provably: "Trust the verified contracts of these functions.
Replace calls to them with their postconditions."

```python
@verified(
    contracts={"isqrt": isqrt.__contract__},
    pre=lambda a: a >= 0,
    post=lambda a, result: result >= 0,
)
def double_sqrt(a: int) -> int:
    s = isqrt(a)
    return s + s
```

`fn.__contract__` is a dict attached by `@verified` containing `pre`, `post`, and
`verified`. Passing it in `contracts=` tells the engine: when it encounters a call to
`isqrt` in the function body, substitute the return value with a fresh Z3 variable
constrained by `isqrt`'s postcondition.

provably derives the proof of `double_sqrt` **without** re-examining `isqrt`'s
implementation.

## Modular verification

This is the classical **assume/guarantee** principle:

$$\frac{P_1 \Rightarrow Q_1 \quad P_2 \land Q_1(x_1) \Rightarrow Q_2}{P_1 \land P_2 \Rightarrow Q_2}$$

- Verify `isqrt` once (establishes $Q_1$).
- Verify `double_sqrt` using $Q_1$ as an assumption (establishes $Q_2$).
- The two proofs are independent — changing `isqrt`'s body invalidates `isqrt.__proof__`
  but not `double_sqrt.__proof__` until you re-run verification.

## Accessing `__contract__`

Every `@verified` function exposes `__contract__`:

```python
isqrt.__contract__
# {'pre': <lambda>, 'post': <lambda>, 'verified': True}
```

Pass this directly to `contracts=` of the calling function:

```python
contracts={"isqrt": isqrt.__contract__}
```

The key must match the function name used in the body (`"isqrt"` in the example above).

## Multiple contracts

Pass a dict with one entry per helper:

```python
@verified(
    contracts={
        "helper_a": helper_a.__contract__,
        "helper_b": helper_b.__contract__,
    },
    post=lambda x, result: result >= 0,
)
def combined(x: int) -> int:
    a = helper_a(x)
    b = helper_b(a)
    return a + b
```

## Unverified callees

If you call a function that is **not** listed in `contracts=` and is not `min`, `max`, or
`abs` (which are handled natively), the translator produces `TRANSLATION_ERROR`:

```
TranslationError: Call to 'helper_a' at line 3 is not a supported builtin and
not listed in contracts=. Add it to contracts= or inline the logic.
```

This is intentional: provably refuses to silently ignore call sites, because doing so
would produce an unsound proof that does not account for what the helper actually returns.

## Re-verification

If you change a helper's implementation, its `__proof__` is invalidated on the next import
(proofs are computed at decoration time). Any caller that depended on the old contracts
should be re-verified. Use `verify_module()` in your test suite to catch this automatically.

```python
# test_proofs.py
from provably.engine import verify_module
import mypackage.math_utils as m

def test_all_proofs_hold():
    results = verify_module(m)
    for name, cert in results.items():
        assert cert.verified, f"{name}: {cert.counterexample}"
```
