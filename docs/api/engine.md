# provably.engine

The verification engine: proof certificates, Z3 orchestration, and cache management.

```python
from provably.engine import ProofCertificate, Status, verify_function, verify_module, clear_cache, configure
from provably.translator import TranslationError
```

Most users only need `ProofCertificate` (via `fn.__proof__`) and `clear_cache()`.

---

## `Status`

```python
class Status(Enum):
    VERIFIED         = "verified"
    COUNTEREXAMPLE   = "counterexample"
    UNKNOWN          = "unknown"
    TRANSLATION_ERROR = "translation_error"
    SKIPPED          = "skipped"
```

The outcome of a Z3 verification attempt.

| Value | Meaning |
|---|---|
| `VERIFIED` | Z3 returned `unsat` — the VC is a mathematical theorem. |
| `COUNTEREXAMPLE` | Z3 returned `sat` — a counterexample was found. |
| `UNKNOWN` | Z3 returned `unknown` — solver timed out or gave up. |
| `TRANSLATION_ERROR` | The AST translator failed to convert the function to Z3. |
| `SKIPPED` | Verification was not attempted (no Z3, async function, or no postcondition). |

---

## `ProofCertificate`

```python
@dataclass(frozen=True)
class ProofCertificate:
    function_name:  str
    source_hash:    str
    status:         Status
    preconditions:  tuple[str, ...]
    postconditions: tuple[str, ...]
    counterexample: dict[str, Any] | None = None
    message:        str = ""
    solver_time_ms: float = 0.0
    z3_version:     str = ""
```

Immutable proof certificate attached to every `@verified` function as `fn.__proof__`.

### Fields

| Field | Type | Description |
|---|---|---|
| `function_name` | `str` | The name of the verified function. |
| `source_hash` | `str` | SHA-256 prefix of the function's source text (content-addressing). |
| `status` | `Status` | The verification outcome. |
| `preconditions` | `tuple[str, ...]` | Human-readable Z3 strings for the applied preconditions. |
| `postconditions` | `tuple[str, ...]` | Human-readable Z3 strings for the applied postconditions. |
| `counterexample` | `dict \| None` | Input values (and `__return__`) that disprove the postcondition. `None` if not applicable. |
| `message` | `str` | Human-readable explanation — error message, skip reason, or counterexample summary. |
| `solver_time_ms` | `float` | Wall-clock milliseconds spent in the Z3 solver. |
| `z3_version` | `str` | The Z3 version string used for this proof. |

### `.verified` property

```python
@property
def verified(self) -> bool:
    return self.status == Status.VERIFIED
```

`True` iff the status is `VERIFIED`.

### `.to_json()` / `.from_json()`

```python
cert.to_json()                        # -> dict[str, Any]  (JSON-serializable)
ProofCertificate.from_json(data)      # -> ProofCertificate
```

Round-trip serialization for storing certificates in CI artifacts, databases, or audit logs.

### Example

```python
from provably import verified

@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
)
def double(x: float) -> float:
    return x * 2

cert = double.__proof__
print(cert.verified)        # True
print(cert.status)          # Status.VERIFIED
print(cert.solver_time_ms)  # e.g. 1.4
print(cert.counterexample)  # None
print(cert)                 # [Q.E.D.] double
```

### Counterexample format

When `status == COUNTEREXAMPLE`, `counterexample` is a dict with one entry per
function parameter (using the original parameter name) plus `__return__` for the
return value:

```python
# {'x': 3, '__return__': 1}  — e.g. for a broken isqrt
```

---

## `TranslationError`

```python
class TranslationError(Exception): ...  # in provably.translator
```

Raised when the AST translator encounters a Python construct it cannot convert to Z3.
Stored as `cert.message` when `cert.status == Status.TRANSLATION_ERROR`.

```python
from provably import verified

@verified(post=lambda x, result: result > 0)
def bad(x: int) -> int:
    for i in range(x):   # unsupported: for loop
        pass
    return x

# cert.status == Status.TRANSLATION_ERROR
# cert.message contains the TranslationError text
```

See [Errors and debugging](../guides/errors.md) for all `TranslationError` messages.

---

## `verify_function()`

```python
verify_function(
    func: Callable,
    pre: Callable | None = None,
    post: Callable | None = None,
    timeout_ms: int | None = None,
    verified_contracts: dict[str, dict] | None = None,
) -> ProofCertificate
```

Low-level entry point used by `@verified`. Most users should use the decorator instead.

Call this directly when you want to verify a function programmatically without decorating it:

```python
from provably.engine import verify_function

def add(x: int, y: int) -> int:
    return x + y

cert = verify_function(
    add,
    pre=lambda x, y: x >= 0,
    post=lambda x, y, result: result >= x,
)
print(cert.verified)  # True
```

---

## `verify_module()`

```python
verify_module(module: types.ModuleType) -> dict[str, ProofCertificate]
```

Find all `@verified` functions in a module and return their certificates.

Returns a dict mapping `function_name` to its `ProofCertificate`. Functions without
a `__proof__` attribute are silently skipped.

```python
import mypackage.math as m
from provably.engine import verify_module

results = verify_module(m)
for name, cert in results.items():
    print(cert)
```

---

## `configure()`

```python
configure(
    timeout_ms: int = 5000,
    raise_on_failure: bool = False,
    log_level: str = "WARNING",
) -> None
```

Set global verification defaults. Must be called before the decorated modules are imported.

| Key | Type | Default | Description |
|---|---|---|---|
| `timeout_ms` | `int` | `5000` | Z3 solver timeout per proof in milliseconds. |
| `raise_on_failure` | `bool` | `False` | Raise `VerificationError` when a proof fails. |
| `log_level` | `str` | `"WARNING"` | Python logging level for the `provably` logger. |

```python
from provably import configure
configure(timeout_ms=10_000, raise_on_failure=True)
```

---

## `clear_cache()`

```python
clear_cache() -> None
```

Clear the global proof cache (content-addressed by source hash + contract bytecode hash).

```python
from provably.engine import clear_cache
clear_cache()
```

::: provably.engine
