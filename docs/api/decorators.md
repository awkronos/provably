# provably.decorators

The public decorator API. Import directly from `provably`:

```python
from provably import verified, runtime_checked
from provably.decorators import VerificationError, ContractViolationError
```

---

## `@verified`

```python
@verified(
    pre=None,
    post=None,
    raise_on_failure=False,
    timeout_ms=None,
    contracts=None,
    check_contracts=False,
)
```

Decorate a function to prove its pre/post contract using Z3.

Runs at **decoration time** (module import). Attaches a `ProofCertificate` to the
function as `fn.__proof__`. The decorated function is **identical** to the original at
call sites — zero overhead unless `check_contracts=True`.

Can be used bare (no parentheses) when only refinement type annotations provide contracts:

```python
@verified                                       # bare — no parentheses
def double(x: Annotated[float, Ge(0)]) -> Annotated[float, Ge(0)]:
    return x * 2
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pre` | `Callable \| None` | `None` | Precondition lambda. Receives the same parameters as the function. Use `&` / `|` / `~` instead of `and` / `or` / `not`. |
| `post` | `Callable \| None` | `None` | Postcondition lambda. Receives function parameters plus `result` as the final argument. |
| `raise_on_failure` | `bool` | `False` | If `True`, raise `VerificationError` immediately when `status != VERIFIED`. |
| `timeout_ms` | `int \| None` | `None` | Per-proof Z3 timeout in milliseconds. Overrides `configure(timeout_ms=...)`. |
| `contracts` | `dict[str, dict] \| None` | `None` | Contracts of helper functions called inside this function, keyed by function name. Enables modular verification. See [Compositionality](../concepts/compositionality.md). |
| `check_contracts` | `bool` | `False` | If `True`, also check pre/post at every call (runtime, not Z3). Defence-in-depth for `SKIPPED` / `UNKNOWN` proofs. |

### Returns

The original function with `__proof__` (`ProofCertificate`) and `__contract__` (dict
with `pre`, `post`, `verified`) attached.

### The `result` convention

The postcondition receives the return value as the **last argument**, named `result`:

```python
@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: result * result <= x,
)
def isqrt(x: int) -> int: ...
```

!!! note "Use `&` not `and` in pre/post lambdas"
    Python's `and` short-circuits and does not produce Z3 `BoolRef` objects.
    Use `&` (bitwise AND) for conjunction in pre/post lambdas:
    ```python
    post=lambda x, y, result: (result >= 0) & (result <= x)
    ```

### `fn.__proof__`

A frozen `ProofCertificate` dataclass. Key fields:

```python
cert = fn.__proof__
cert.verified        # bool — True iff status == VERIFIED
cert.status          # Status enum: VERIFIED / COUNTEREXAMPLE / UNKNOWN / ...
cert.counterexample  # dict | None — {'param': value, ..., '__return__': value}
cert.solver_time_ms  # float — milliseconds
cert.message         # str — human-readable summary
```

### Example

```python
from provably import verified

@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b

print(modulo.__proof__.verified)   # True
print(modulo.__proof__)            # [Q.E.D.] modulo
```

---

## `@runtime_checked`

```python
@runtime_checked(
    pre=None,
    post=None,
    raise_on_failure=True,
)
```

Decorate a function to check its pre/post contract **at every call**, using Python
evaluation rather than Z3.

Does not require `z3-solver`. Does not produce a `ProofCertificate`. Use this when:

- You want contract checking without installing Z3.
- The function body uses unsupported constructs (loops, strings, etc.).
- You want defence-in-depth runtime checking alongside a static proof.

Raises `ContractViolationError` on violation by default.

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pre` | `Callable \| None` | `None` | Precondition. Evaluated with the actual call arguments before the function runs. Must return truthy when the precondition holds. |
| `post` | `Callable \| None` | `None` | Postcondition. Evaluated with actual arguments plus `result` after the function returns. |
| `raise_on_failure` | `bool` | `True` | If `True` (default), raise `ContractViolationError`. If `False`, log a warning instead. |

### Example

```python
from provably import runtime_checked

@runtime_checked(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
)
def sqrt_approx(x: float) -> float:
    return x ** 0.5

sqrt_approx(4.0)   # ok — returns 2.0
sqrt_approx(-1.0)  # raises ContractViolationError: Precondition violated for 'sqrt_approx' with args (-1.0,)
```

---

## `VerificationError`

```python
class VerificationError(Exception):
    certificate: ProofCertificate
```

Raised by `@verified` when `raise_on_failure=True` and the proof fails (status is
`COUNTEREXAMPLE`, `UNKNOWN`, or `TRANSLATION_ERROR`). The failing `ProofCertificate`
is available as `exc.certificate`.

```python
from provably.decorators import VerificationError

try:
    @verified(raise_on_failure=True, post=lambda x, result: result > x)
    def bad_double(x: int) -> int:
        return x   # BUG: should be x * 2
except VerificationError as e:
    print(e.certificate.counterexample)  # {'x': 0, '__return__': 0}
```

---

## `ContractViolationError`

```python
class ContractViolationError(Exception):
    kind:      str         # "pre" or "post"
    func_name: str
    args_:     tuple
    result:    Any | None  # set for "post" violations
```

Raised by `@runtime_checked` (and by `@verified` with `check_contracts=True`) when a
pre or postcondition is violated at call time.

::: provably.decorators
