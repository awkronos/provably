# Pytest Integration

Proofs are computed at decoration time (when the module is imported). In pytest, you assert
`__proof__.verified` directly in test functions — no special runner, no plugin, no configuration.

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
    assert cert.verified, f"integer_sqrt proof failed:\n{cert}"
```

When a proof fails, the assertion error message includes the full `ProofCertificate` —
status, counterexample, and Z3 timing.

---

## `verify_module()` — one test for the whole package

`verify_module()` collects every `@verified` function in a module and returns a dict
mapping function name to `ProofCertificate`. Use it for a single test that covers your
entire proof surface:

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

Add this to CI and every proof regression is caught on every push.

---

## `raise_on_failure=True`

Pass `raise_on_failure=True` to raise `VerificationError` immediately at decoration time
when a proof fails. Useful during development — the import itself fails loudly:

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

For CI, prefer explicit assertions so all proof failures are reported in a single run.

---

## Clearing the proof cache

provably caches proof results by function identity. If you mutate module state between
tests, call `clear_cache()` to force re-verification:

```python
from provably.engine import clear_cache

def setup_function():
    clear_cache()
```

provably's own test suite does this via an `autouse` fixture:

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

## CI configuration

```yaml
# .github/workflows/ci.yml  (excerpt)
- name: Run proof tests
  run: uv run pytest tests/ -v -m proof --cov=src/provably
```

Proof assertions run as normal pytest tests. If any proof fails — counterexample found,
translation error, or timeout — the test fails and CI blocks.

---

## Recommended test structure

```
tests/
├── conftest.py          # requires_z3 mark, clear_cache autouse fixture
├── test_proofs.py       # @verified assertions — one test per function
├── test_runtime.py      # @runtime_checked call-time contract tests
└── test_integration.py  # verify_module() over entire packages
```

Keep proof tests separate from behavioral tests. Proof tests are deterministic and fast
(milliseconds per proof). Mark them `@pytest.mark.proof` for selective execution:

```bash
pytest -m proof           # proofs only
pytest -m "not proof"     # behavioral tests only
pytest tests/test_proofs.py -v  # verbose proof output with timing
```
