# Errors and Debugging

## Counterexamples

When `cert.status == Status.COUNTEREXAMPLE`, Z3 found an input violating the contract:

```python
from provably import verified

@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result * result == n,
)
def isqrt(n: int) -> int:
    r = 0
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r

cert = isqrt.__proof__
cert.verified        # False
cert.status          # Status.COUNTEREXAMPLE
cert.counterexample  # {'n': 2, '__return__': 1}
# isqrt(2) = 1, but 1*1 != 2
```

Fields: one entry per parameter (original names) plus `__return__` for the return value.

---

## `TranslationError`

Raised at decoration time when the translator encounters an unsupported construct.

| Message | Fix |
|---|---|
| `Unsupported node type: While` | Remove the loop. Use closed-form or a `@verified` helper. |
| `Call to 'f' is not in contracts=` | Add to `contracts=` with its own proof, or inline. |
| `Module constant 'X' has type str` | Only `int`/`float` constants are supported. |
| `Exponent must be a concrete integer literal` | Replace `x ** n` with `x ** 2` or `x * x`. |
| `No Z3 sort for Python type: list` | Only `int`, `float`, `bool`, `Annotated` wrappers. |

---

## `UNKNOWN` (timeout)

```python
cert = f.__proof__
cert.status   # Status.UNKNOWN
cert.message  # "Z3 returned unknown (timeout 5000ms?)"
```

Not a proof failure -- the solver didn't finish.

**Fix:**

1. **Increase timeout:**
    ```python
    from provably import configure
    configure(timeout_ms=30_000)
    ```
    Then `clear_cache()` and re-import.

2. **Eliminate nonlinear terms.** `result == a * b` with both symbolic is undecidable.

3. **Split the function** into smaller `@verified` helpers with `contracts=`.

4. **Fall back to `@runtime_checked`.**

---

## `inspect.getsource` failures

```
OSError: could not get source code
```

Function defined in a REPL, `exec()`, or dynamically generated module.
Fix: move it to a `.py` file.

---

## Import errors with `raise_on_failure=True`

If importing raises `VerificationError`, the entire test module fails to collect.
Debug by temporarily disabling:

```python
from provably import configure
configure(raise_on_failure=False)

import mypackage.math
cert = mypackage.math.my_function.__proof__
cert.status          # inspect the status
cert.counterexample  # inspect the witness
cert.message         # inspect the error
```
