# Pytest Integration

Proofs are computed at import time. Assert `__proof__.verified` in tests --
no plugin, no configuration.

## Basic assertions

```python
# tests/test_proofs.py
from mypackage.math import clamp, safe_divide, integer_sqrt

def test_clamp_proven():
    assert clamp.__proof__.verified

def test_safe_divide_proven():
    assert safe_divide.__proof__.verified

def test_integer_sqrt_proven():
    cert = integer_sqrt.__proof__
    assert cert.verified, f"Proof failed:\n{cert}"
```

---

## `verify_module()` -- batch verification

```python
# tests/test_all_proofs.py
import mypackage.math_utils as m
from provably.engine import verify_module

def test_all_proofs():
    results = verify_module(m)
    failures = {name: cert for name, cert in results.items() if not cert.verified}
    assert not failures, (
        "Proof failures:\n" + "\n".join(f"  {n}: {c}" for n, c in failures.items())
    )
```

---

## `raise_on_failure=True`

Raises `VerificationError` at decoration time. The import itself fails:

```python
@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
    raise_on_failure=True,
)
def safe_sqrt(x: float) -> float:
    return x ** 0.5
```

For CI, prefer explicit assertions so all failures are reported in one run.

---

## Cache management

```python
# conftest.py
import pytest
from provably.engine import clear_cache

@pytest.fixture(autouse=True)
def fresh_cache():
    clear_cache()
    yield
    clear_cache()
```

---

## CI

```yaml
# .github/workflows/ci.yml
- name: Run proof tests
  run: uv run pytest tests/ -v -m proof
```

---

## Recommended structure

```
tests/
├── conftest.py          # clear_cache autouse fixture
├── test_proofs.py       # @verified assertions
├── test_runtime.py      # @runtime_checked tests
└── test_integration.py  # verify_module() over packages
```

```bash
pytest -m proof           # proofs only
pytest -m "not proof"     # behavioral tests only
```
