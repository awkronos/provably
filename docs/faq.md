# FAQ

## Why can't I use `and`/`or`/`not` in contracts?

```python
# Wrong -- Python short-circuits, drops the first conjunct
@verified(post=lambda x, result: result >= 0 and result <= 100)

# Correct -- Z3 builds a symbolic conjunction
@verified(post=lambda x, result: (result >= 0) & (result <= 100))
```

Python's `and`/`or`/`not` cannot be overloaded. `a & b` on `z3.BoolRef` invokes
`__and__` and returns a symbolic expression. `a and b` short-circuits in Python
and never reaches Z3.

Parentheses required: `&` has lower precedence than `>=`.

---

## Are while loops supported?

Yes, as of 0.3.0. Bounded `while` loops are unrolled up to 256 iterations, the same
as `for i in range(N)`. The translator determines the bound from the precondition and
loop condition.

```python
@verified(
    pre=lambda n: (n >= 0) & (n <= 10),
    post=lambda n, result: result == 0,
)
def countdown(n: int) -> int:
    while n > 0:
        n = n - 1
    return n
# countdown.__proof__.verified -> True
```

If the bound cannot be determined or exceeds 256, provably raises `TranslationError`.
See [Supported Python](guides/supported-python.md).

---

## What does "TCB" mean?

Trusted Computing Base -- components whose correctness is assumed, not proved.

| Component | Risk |
|---|---|
| Python AST parser | Source must match bytecode |
| `Translator` (~500 LOC) | Mistranslation = proof of wrong formula |
| Z3 | Must implement SMT correctly |
| CPython | Executes everything |

`VERIFIED` means: *assuming the TCB is correct, the contract holds for all inputs
satisfying the precondition.* See [Soundness](concepts/soundness.md).

---

## Is this a replacement for unit tests?

No. Complementary.

| Concern | `@verified` | Tests |
|---|---|---|
| All inputs (precondition-bounded) | Yes | No |
| Integration / I/O / network | No | Yes |
| Performance | No | Yes |
| Concurrency | No | Yes |
| Unsupported constructs | `TRANSLATION_ERROR` | Yes |

Use `@verified` for pure functions with mathematical contracts.
Use tests for everything else.
Use `@runtime_checked` as defense-in-depth between them.

---

## How fast is verification?

1--20ms typical for linear arithmetic. 100ms--5s for complex nonlinear contracts.
Default timeout: 5000ms.

```python
@verified(post=lambda x, result: result >= 0, timeout_ms=10_000)
def complex_function(x: float) -> float: ...
```

```python
from provably import configure
configure(timeout_ms=10_000)  # global
```

Results are cached by source hash. Re-import returns the cached certificate.

---

## What if Z3 times out?

`Status.UNKNOWN` -- not a proof failure, just "didn't finish."

1. Increase `timeout_ms`.
2. Simplify the contract or eliminate nonlinear terms.
3. Split into smaller `@verified` helpers with `contracts=`.
4. Use `@runtime_checked` as a fallback.

---

## Can I verify functions that call external libraries?

Not statically. Use `contracts=` for provably-verified callees:

```python
@verified(
    post=lambda x, result: result >= 0,
    contracts={"my_abs": my_abs.__contract__},
)
def double_abs(x: float) -> float:
    return my_abs(x) * 2
# double_abs.__proof__.verified -> True
```

For external calls: wrap in a `@verified` stub with a manually stated contract,
or use `@runtime_checked`. See [Compositionality](concepts/compositionality.md).

---

## Does it work with mypy/pyright?

Yes. provably ships `py.typed`. Refinement markers are `typing.Annotated` values --
type checkers see `Annotated[float, Ge(0)]` as `float`.

The `__proof__` attribute is dynamic. Access it via:

```python
cert = typing.cast(ProofCertificate, getattr(my_func, "__proof__"))
```

---

## `@verified` vs `@runtime_checked`

| | `@verified` | `@runtime_checked` |
|---|---|---|
| When | Import time | Every call |
| Requires Z3 | Yes | No |
| Coverage | All inputs (proof) | Only inputs passed |
| Call-site overhead | Thin wrapper (no solver) | One lambda eval |
| Counterexamples | Automatic | N/A |
| Unsupported constructs | `TranslationError` | Always works |

Combine with `check_contracts=True` for defense-in-depth:

```python
@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
    check_contracts=True,   # also enforces at runtime
)
def sqrt_approx(x: float) -> float:
    return x ** 0.5
```

---

## Can provably use Lean4 instead of Z3?

Yes. The `provably.lean4` module translates Python functions + contracts into Lean4
theorem files and type-checks them with the Lean4 compiler.

```python
from provably import verify_with_lean4

cert = verify_with_lean4(
    my_func,
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
)
cert.status  # Status.VERIFIED (if Lean4 closes the proof)
```

Use cases:

- **Cross-checking**: verify the same contract with both Z3 and Lean4 for higher assurance.
- **Exporting**: `export_lean4(func, pre=, post=, output_path="theorem.lean")` generates
  a standalone `.lean` file for inclusion in a larger Lean4 project.
- **De Bruijn kernel**: Lean4's type checker has a verified kernel, providing a different
  trust basis than Z3's SMT solver.

When Lean4 is not installed, `verify_with_lean4()` returns a `SKIPPED` certificate.
Install via: `brew install elan-init && elan default stable`.

See [API: provably.lean4](api/lean4.md) for full details.

---

## Can provably prove itself?

Yes. Sixteen self-proofs, all `VERIFIED`, enforced on every push.
See [Self-Proof](self-proof.md).
