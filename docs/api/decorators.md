# provably.decorators

```python
from provably import verified, runtime_checked
from provably.decorators import VerificationError, ContractViolationError
```

---

## `@verified`

Prove a function's pre/post contract using Z3 at decoration time. Attaches a
`ProofCertificate` as `fn.__proof__`. No solver runs at call time. A thin
`functools.wraps` wrapper is applied; `check_contracts=True` adds runtime contract checks.

```python
@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b

modulo.__proof__.verified  # True
str(modulo.__proof__)      # "[Q.E.D.] modulo"
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pre` | `Callable \| None` | `None` | Precondition. Same params as function. Use `&`/`\|`/`~`. |
| `post` | `Callable \| None` | `None` | Postcondition. Params + `result` (last arg). |
| `raise_on_failure` | `bool` | `False` | Raise `VerificationError` if proof fails. |
| `timeout_ms` | `int \| None` | `None` | Per-proof Z3 timeout. Overrides `configure()`. |
| `contracts` | `dict \| None` | `None` | Helper contracts for modular verification. |
| `check_contracts` | `bool` | `False` | Also enforce pre/post at runtime. |

!!! warning "Use `&` not `and` in pre/post lambdas"
    `and` short-circuits and silently drops conjuncts. See [Contracts](../concepts/contracts.md).

---

## `@runtime_checked`

Check pre/post at every call using Python evaluation. No Z3 required.

```python
@runtime_checked(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
)
def sqrt_approx(x: float) -> float:
    return x ** 0.5

sqrt_approx(4.0)   # 2.0
sqrt_approx(-1.0)  # raises ContractViolationError
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pre` | `Callable \| None` | `None` | Precondition. Evaluated with actual arguments. |
| `post` | `Callable \| None` | `None` | Postcondition. Arguments + `result`. |
| `raise_on_failure` | `bool` | `True` | Raise `ContractViolationError`. If `False`, log warning. |

---

## `VerificationError`

Raised by `@verified(raise_on_failure=True)` when proof fails.

```python
try:
    @verified(raise_on_failure=True, post=lambda x, result: result > x)
    def bad(x: int) -> int:
        return x
except VerificationError as e:
    e.certificate.counterexample  # {'x': 0, '__return__': 0}
```

---

## `ContractViolationError`

Raised by `@runtime_checked` (or `@verified(check_contracts=True)`) on violation.

```python
class ContractViolationError(Exception):
    kind:      str         # "pre" or "post"
    func_name: str
    args_:     tuple
    result:    Any | None  # set for "post" violations
```

---

::: provably.decorators
