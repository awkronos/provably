# provably.engine

Proof certificates, Z3 orchestration, and cache management.

```python
from provably.engine import ProofCertificate, Status, verify_function, verify_module, clear_cache, configure
```

---

## `Status`

| Value | Meaning |
|---|---|
| `VERIFIED` | Z3 returned `unsat`. Mathematical theorem. |
| `COUNTEREXAMPLE` | Z3 returned `sat`. Counterexample found. |
| `UNKNOWN` | Solver timed out. |
| `TRANSLATION_ERROR` | AST translator failed. |
| `SKIPPED` | Not attempted (no Z3, async, no postcondition). |

---

## `ProofCertificate`

Immutable certificate attached to every `@verified` function as `fn.__proof__`.

```python
cert = fn.__proof__
cert.verified        # True iff status == VERIFIED
cert.status          # Status.VERIFIED
cert.counterexample  # {'x': 3, '__return__': 1} or None
cert.solver_time_ms  # 1.4
cert.message         # human-readable summary
str(cert)            # "[Q.E.D.] fn_name"
```

| Field | Type | Description |
|---|---|---|
| `function_name` | `str` | Verified function name |
| `source_hash` | `str` | SHA-256 prefix (content-addressing) |
| `status` | `Status` | Verification outcome |
| `preconditions` | `tuple[str, ...]` | Z3 precondition strings |
| `postconditions` | `tuple[str, ...]` | Z3 postcondition strings |
| `counterexample` | `dict \| None` | Witness on `COUNTEREXAMPLE` |
| `message` | `str` | Error/skip/counterexample summary |
| `solver_time_ms` | `float` | Wall-clock ms in Z3 |
| `z3_version` | `str` | Z3 version used |

### Serialization

```python
data = cert.to_json()                    # dict (JSON-serializable)
cert = ProofCertificate.from_json(data)  # round-trip
```

---

## `verify_function()`

Low-level entry point. Most users should use `@verified` instead.

```python
from provably.engine import verify_function

def add(x: int, y: int) -> int:
    return x + y

cert = verify_function(add, pre=lambda x, y: x >= 0, post=lambda x, y, result: result >= x)
cert.verified  # True
```

---

## `verify_module()`

Collect all `@verified` functions in a module, return `{name: ProofCertificate}`.

```python
from provably.engine import verify_module
import mypackage.math as m

results = verify_module(m)
for name, cert in results.items():
    print(cert)  # [Q.E.D.] name
```

---

## `configure()`

Set global defaults. Call before importing decorated modules.

| Key | Default | Description |
|---|---|---|
| `timeout_ms` | `5000` | Z3 timeout per proof (ms) |
| `raise_on_failure` | `False` | Raise `VerificationError` on failure |
| `log_level` | `"WARNING"` | Logging level for `provably` logger |

```python
from provably import configure
configure(timeout_ms=10_000, raise_on_failure=True)
```

---

## `clear_cache()`

Clear the global proof cache (content-addressed by source + contract hash).

```python
from provably.engine import clear_cache
clear_cache()
```

---

::: provably.engine
