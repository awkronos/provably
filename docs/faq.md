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

## Why no while loops?

Z3's quantifier-free arithmetic is decidable -- the solver always terminates.
While loops make verification undecidable: you need a loop invariant, and invariant
synthesis is an open research problem. provably rejects them with `TranslationError`.

Bounded `for i in range(N)` with literal `N` is supported (unrolled up to 256 iterations).
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

## Can provably prove itself?

Yes. Ten self-proofs, all `VERIFIED`, enforced on every push.
See [Self-Proof](self-proof.md).
