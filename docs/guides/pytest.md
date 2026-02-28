# Pytest Integration

Proofs are computed at decoration time (when the module is imported). In pytest, this means
you can assert `__proof__.verified` directly in test functions — no special runner needed.

## Basic assertion

```python
# tests/test_proofs.py
from mypackage.math import clamp, safe_divide, integer_sqrt

def test_clamp_proven():
    assert clamp.__proof__.verified

def test_safe_divide_proven():
    assert safe_divide.__proof__.verified

def test_integer_sqrt_proven():
    assert integer_sqrt.__proof__.verified
```

If a proof fails, the assertion error message tells you which function failed. Add a
custom message to expose the counterexample:

```python
def test_integer_sqrt_proven():
    cert = integer_sqrt.__proof__
    assert cert.verified, (
        f"integer_sqrt proof failed: {cert}"
    )
```

## `raise_on_failure=True`

Pass `raise_on_failure=True` to `@verified` to raise `VerificationError` immediately at
decoration time when a proof fails, rather than storing the failure in `__proof__`:

```python
from provably import verified

@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
    raise_on_failure=True,
)
def safe_sqrt(x: float) -> float:
    return x ** 0.5
```

This is useful for development: the import itself fails loudly rather than silently storing
a failed proof. For CI, prefer explicit assertions so all proof failures are reported in a
single test run.

## `verify_module()`

`verify_module()` collects every `@verified` function in a module and returns a
dict mapping function name to `ProofCertificate`:

```python
# tests/test_all_proofs.py
import mypackage.math_utils as m
from provably.engine import verify_module

def test_all_proofs():
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

This gives you a single test that catches any proof regression across the entire module.
Add it to your CI test suite and it runs automatically on every push.

## Skipping Z3 when not installed

Use the `requires_z3` fixture from provably's `conftest.py` to skip proof tests when
`z3-solver` is not installed:

```python
# conftest.py (already in provably's test suite — copy for your project)
import pytest
try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False

requires_z3 = pytest.mark.skipif(not HAS_Z3, reason="z3-solver not installed")
```

```python
# tests/test_proofs.py
from conftest import requires_z3
from mypackage.math import clamp

@requires_z3
def test_clamp_proven():
    assert clamp.__proof__.verified
```

## Clearing the proof cache

provably caches proof results by function identity. Between tests that mutate module state,
call `clear_cache()` to force re-verification:

```python
from provably.engine import clear_cache

def setup_function():
    clear_cache()
```

The `conftest.py` in provably's own test suite does this automatically via an `autouse`
fixture.

## Example CI configuration

```yaml
# .github/workflows/ci.yml  (excerpt)
- name: Run tests
  run: uv run pytest tests/ -v --cov=src/provably
```

Proof assertions run as normal pytest tests. If any proof fails (counterexample found,
translation error, or timeout), the test fails and CI blocks.

## Recommended test structure

```
tests/
├── conftest.py          # requires_z3 mark, clear_cache autouse fixture
├── test_proofs.py       # @verified assertions — one test per function
├── test_runtime.py      # @runtime_checked call-time contract tests
└── test_integration.py  # verify_module() over entire packages
```

Keep proof tests in a separate file from behavioral tests. Proof tests are deterministic
and fast (milliseconds per proof). Mark them `@pytest.mark.proof` for selective execution:

```bash
pytest -m proof          # proofs only
pytest -m "not proof"    # behavioral tests only
```
