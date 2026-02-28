# Errors and Debugging

## Counterexamples

When `cert.status == Status.COUNTEREXAMPLE`, Z3 found an input violating the contract:

```python
from provably import verified

@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result * result == n,  # wrong: n//2 is not sqrt
)
def bad_sqrt(n: int) -> int:
    return n // 2

cert = bad_sqrt.__proof__
cert.verified        # False
cert.status          # Status.COUNTEREXAMPLE
cert.counterexample  # {'n': 3, '__return__': 1}
# 3 // 2 = 1, but 1*1 != 3
```

Fields: one entry per parameter (original names) plus `__return__` for the return value.

!!! note "While loops produce `TRANSLATION_ERROR`, not counterexamples"
    If the function body uses a `while` loop, the translator rejects it
    before Z3 runs. The status will be `TRANSLATION_ERROR`, not `COUNTEREXAMPLE`.

---

## `TranslationError`

Raised at decoration time when the translator encounters an unsupported construct.

| Message | Fix |
|---|---|
| `Unsupported statement: While` | Remove the loop. Use closed-form or a `@verified` helper. |
| `Unknown function 'f' ... Add @verified or register in verified_contracts` | Add to `contracts=` with its own proof, or inline. |
| `String constant '...' not supported` | Only `int`/`float`/`bool` constants are supported. |
| `Only constant integer exponents 0–3 supported for **` | Replace `x ** n` with `x ** 2` or `x * x`. |
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
