# Errors and Debugging

## Reading counterexamples

When `cert.status == Status.COUNTEREXAMPLE`, Z3 found a counterexample.
It is available as a `dict` on `cert.counterexample`:

```python
from provably import verified
from provably.engine import Status

@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result * result == n,   # wrong: isqrt doesn't always square back
)
def isqrt(n: int) -> int:
    r = 0
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r

cert = isqrt.__proof__
print(cert.verified)        # False
print(cert.status)          # Status.COUNTEREXAMPLE
print(cert.counterexample)  # {'n': 2, '__return__': 1}
# Explanation: isqrt(2) = 1, but 1 * 1 = 1 != 2
```

The counterexample shows the exact input values (`n=2`) and the return value (`__return__=1`)
that together violate the postcondition. This is a **concrete witness** — you can run
`isqrt(2)` yourself and observe the behavior.

### Counterexample fields

The keys in `counterexample` are:

- One entry per function parameter (using the original parameter names).
- One entry named `__return__` for the return value.

For functions with no precondition, the counterexample is the minimal-magnitude witness
Z3 found. Z3 does not guarantee minimality in general, but for integers it often produces
small values.

---

## `TranslationError`

`TranslationError` is raised at decoration time when the translator encounters a Python
construct it cannot convert to Z3. The error message includes the offending AST node and
line number.

### Common messages

**"Unsupported node type: `While`"**

```
provably.engine.TranslationError: Unsupported node type: While at line 4.
  While loops cannot be translated to Z3 (termination is undecidable).
  Refactor: extract the loop body into a helper with its own @verified contract,
  or replace with a closed-form expression.
```

Fix: Remove the `while` loop from the verified function's body. Either replace it with a
closed-form expression, or — if the loop is inherently part of the algorithm — verify a
weaker property that doesn't require inlining the loop.

---

**"Call to 'f' is not in contracts= and is not a supported builtin"**

```
provably.engine.TranslationError: Call to 'helper' at line 7 is not a supported builtin
and not listed in contracts=. Add it to contracts=[helper] or inline the logic.
```

Fix: Add the callee to `contracts=` with its own `@verified` decorator, or inline its logic.

---

**"Module constant 'X' has type <class 'str'>, expected int or float"**

```
provably.engine.TranslationError: Module constant 'LABEL' has type <class 'str'>,
expected int or float. Only numeric constants can be injected into Z3 expressions.
```

Fix: Do not reference string constants from contracts or the function body being translated.
Pass them as parameters or guard the reference outside the translated path.

---

**"Exponent must be a concrete integer literal, got Name('n')"**

```
provably.engine.TranslationError: Exponent in x**n must be a concrete integer literal.
Symbolic exponents are not representable in Z3 linear arithmetic.
```

Fix: Replace `x ** n` with a concrete power (`x ** 2`, `x ** 3`) or use repeated multiplication.

---

**"No Z3 sort for Python type: list"**

```
provably.engine.TranslationError: No Z3 sort for Python type: list[int].
provably supports int, float, bool, and Annotated wrappers of these.
```

Fix: Remove list parameters from the verified function or refactor to a numeric interface.

---

## Debugging `UNKNOWN` (timeout)

When `cert.status == Status.UNKNOWN`:

```python
from provably.engine import Status

cert = f.__proof__
print(cert.verified)                        # False
print(cert.status == Status.UNKNOWN)        # True
print(cert.message)                         # "Z3 returned unknown (timeout 5000ms?)"
```

This means Z3 exhausted its timeout budget without determining satisfiability. It is **not**
a proof failure — the property may still hold. Strategies:

### 1. Increase the timeout

```python
from provably import configure
configure(timeout_ms=30_000)   # 30 seconds (default: 5000)
```

Re-run the proof by calling `clear_cache()` and re-importing the module (or restarting the
process).

### 2. Identify nonlinear arithmetic

Timeout is most common when the function or contracts contain products of two symbolic
variables:

```python
post=lambda a, b, result: result == a * b   # a * b is nonlinear if both are symbolic
```

Nonlinear integer arithmetic is undecidable in general; Z3 uses incomplete heuristics.
Try to reformulate: can you express the property in terms of `a` and `b` separately?

### 3. Simplify the function

Break the function into smaller `@verified` helpers and compose with `contracts=`.
Each sub-proof is easier for Z3 to close.

### 4. Use `@runtime_checked` as a fallback

If the property cannot be proven statically, use `@runtime_checked` to assert it at
every call:

```python
from provably import runtime_checked

@runtime_checked(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
)
def complex_fn(x: float) -> float:
    ...
```

This does not produce a proof certificate but adds safety at call time.

---

## `inspect.getsource` failures

If provably raises:

```
OSError: could not get source code
```

The function was defined in a context where source is not available (REPL, `exec()`,
dynamically generated module). provably requires readable source files.

Fix: Move the function to a `.py` file.

---

## Proof-on-import errors in test suite

If importing a module raises `VerificationError` (when `raise_on_failure=True`), the
entire test module fails to import and pytest reports a collection error. To debug:

```python
# Temporarily disable raise_on_failure:
from provably import configure
configure(raise_on_failure=False)

# Now import and inspect:
import mypackage.math
cert = mypackage.math.my_function.__proof__
print(cert.counterexample)
print(cert.message)
```
