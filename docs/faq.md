# FAQ

Precise answers to common questions about provably, Z3, and formal verification.

---

## Why can't I use `and`/`or`/`not` in contracts?

Python's `and`, `or`, and `not` are boolean short-circuit operators built into
the language grammar. They cannot be overloaded. When you write `a and b`,
Python evaluates `a`, and if it is falsy, returns `a` without evaluating `b`.
This happens before Z3 ever sees the expression.

Z3 uses operator overloading to build symbolic expression trees. When you
write `a & b` on two `z3.BoolRef` objects, Z3's `__and__` method runs and
returns a new `z3.BoolRef` representing the conjunction. The & operator *can*
be overloaded; `and` cannot.

**Use `&` for AND, `|` for OR, `~` for NOT** in all pre/post lambdas:

```python
# Wrong — Python evaluates this eagerly, returns a Python bool
@verified(post=lambda x, result: result >= 0 and result <= 100)
def f(x): ...

# Correct — Z3 builds a symbolic conjunction
@verified(post=lambda x, result: (result >= 0) & (result <= 100))
def f(x): ...
```

The parentheses around each comparison are required because `&` has lower
precedence than `>=` in Python.

---

## Why doesn't provably support while loops?

Z3's quantifier-free linear arithmetic is *decidable*, meaning the solver
always terminates with a definitive answer. While loops can iterate an
unbounded number of times, making the verification problem undecidable in
general: you would need to find a *loop invariant* that holds before every
iteration and implies the postcondition after the loop terminates.

Loop invariant synthesis is an active research area. Some tools (Dafny,
Frama-C, VeriFast) require the programmer to supply invariants as
annotations. provably's design goal is zero annotation overhead — contracts
only, no invariants — so while loops are currently unsupported and receive
`TranslationError`.

`for` loops over small known ranges are planned. Recursive functions with
bounded depth are partially supported via unrolling. If your use case
requires while loops, see [Supported Python](guides/supported-python.md)
for alternatives, or open an issue describing your contract.

---

## What does "TCB" mean?

Trusted Computing Base. In formal verification, the TCB is the set of
components whose correctness must be *assumed* rather than proved. A smaller
TCB means fewer things can go wrong silently.

provably's TCB includes:

- **Python's AST parser** — the source text must accurately reflect what CPython executes.
- **provably's translator** (`translator.py`) — it must map Python semantics to Z3 semantics faithfully. A translation bug produces a proof of the wrong formula, which is the primary failure mode.
- **Z3** — the SMT solver must implement its decision procedure correctly.
- **CPython** — the runtime that executes everything.

When a proof is `VERIFIED`, it means: *assuming the TCB is correct, the
contract holds for all inputs satisfying the precondition.* This is still
a substantially stronger guarantee than any test suite, which only exercises
finitely many inputs.

See [Soundness](concepts/soundness.md) for the full epistemological picture.

---

## Is this a replacement for unit tests?

No. They are complementary.

A `VERIFIED` proof covers *all possible inputs* satisfying the precondition,
which a test suite cannot. But tests verify things provably cannot:

- **Integration behavior** — what happens when your function talks to a database,
  a network, or a filesystem.
- **Performance** — proofs say nothing about runtime complexity.
- **Concurrency** — the translator is single-threaded and sequential.
- **Dynamic dispatch** — proofs assume the function body as written; if a
  method is overridden, the proof does not follow.
- **Unsupported constructs** — anything that produces `TranslationError` or
  `SKIPPED` must be tested conventionally.

The recommended workflow: use `@verified` for pure functions with clear
mathematical contracts, and use unit tests + integration tests for everything
else. Use `@runtime_checked` as a defense-in-depth layer between them.

---

## How fast is Z3 verification?

For the functions provably currently supports (linear arithmetic, simple
branching, integer/float operations), Z3 typically closes proofs in **1–20ms**.
More complex contracts with many variables or nonlinear arithmetic may take
100ms–5s.

The default timeout is **5000ms** (5 seconds). Functions that exceed it receive
status `UNKNOWN`. You can adjust per-decorator:

```python
@verified(post=lambda x, result: result >= 0, timeout_ms=10_000)
def complex_function(x: float) -> float: ...
```

Or globally:

```python
from provably import configure
configure(timeout_ms=10_000)
```

Z3 results are cached by source hash. If you re-import a module or call
`@verified` on an already-decorated function, the cached certificate is
returned immediately without re-running Z3.

---

## What happens if Z3 times out?

The proof attempt returns `Status.UNKNOWN`. The `ProofCertificate` carries
`verified=False` and `status=Status.UNKNOWN`.

If `raise_on_failure=True`, a timeout raises `VerificationError`. Otherwise,
the function is silently wrapped with no static guarantee — only its runtime
behavior is unchanged.

Timeouts are not treated as proof failures (unlike `COUNTEREXAMPLE`), because
a timeout only says "we didn't finish" — it does not mean the contract is
false. To deal with `UNKNOWN` results:

1. Increase `timeout_ms`.
2. Simplify the contract.
3. Split the function into smaller provable pieces.
4. Use `@runtime_checked` as a runtime guard while the static proof remains open.

---

## Can I verify functions that call external libraries?

Not statically. If your function calls `math.sqrt`, `numpy.sum`, or any
function that is not itself `@verified` with a known contract, the translator
cannot reason about that call's result.

provably's compositionality mechanism handles *provably-verified* callees:

```python
@verified(post=lambda x, result: result >= 0)
def my_abs(x: float) -> float:
    return x if x >= 0 else -x

@verified(
    post=lambda x, result: result >= 0,
    contracts={"my_abs": my_abs.__contract__},
)
def double_abs(x: float) -> float:
    return my_abs(x) * 2  # provably knows my_abs returns >= 0
```

For external functions, the options are:

- Wrap the external call in a `@verified` stub with a manually stated contract
  and `SKIPPED` status, and trust the contract as an axiom.
- Use `@runtime_checked` to guard the call at runtime.
- Restrict the function body to constructs the translator supports.

See [Compositionality](concepts/compositionality.md) for the full pattern.

---

## Does provably work with mypy/pyright?

Yes, for the most part. provably is fully typed and ships a `py.typed` marker.
Refinement type markers (`Ge`, `Le`, `Between`, etc.) are typed as
`typing.Annotated` values, which mypy and pyright understand structurally — they
see `Annotated[float, Ge(0)]` as `float`.

The one gap: `func.__proof__` is attached dynamically by the decorator, and
the type stubs use `# type: ignore` comments to suppress the attribute errors.
If you access `__proof__` frequently, cast or use `hasattr`:

```python
from provably.engine import ProofCertificate
import typing

cert = typing.cast(ProofCertificate, getattr(my_func, "__proof__"))
```

A `Protocol` for verified functions is on the roadmap for a future release.

---

## What's the difference between `@verified` and `@runtime_checked`?

| | `@verified` | `@runtime_checked` |
|---|---|---|
| **When** | At decoration time (import) | At every call |
| **Requires Z3** | Yes | No |
| **Coverage** | All inputs (proof) | Only inputs actually passed |
| **Overhead at call site** | Zero | One lambda evaluation per call |
| **Counterexamples** | Concrete, automatic | N/A — violation is the counterexample |
| **Unsupported constructs** | `TranslationError` → `SKIPPED` | Always works |

Use `@verified` when you want a proof. Use `@runtime_checked` when you want
an assertion. Combine them with `check_contracts=True`:

```python
@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
    check_contracts=True,  # also enforces at runtime
)
def sqrt_approx(x: float) -> float:
    return x ** 0.5
```

`check_contracts=True` adds runtime enforcement even when the static proof
succeeds, giving defense-in-depth against TCB failures.

---

## Can provably prove itself?

Yes — and it does, on every push to `main`. See the [Self-Proof](self-proof.md)
page for the full explanation.

The short version: `src/provably/_self_proof.py` contains ten pure functions
decorated with `@verified`. They are provably's own reference implementations
of `min`, `max`, `abs`, `clamp`, `relu`, division, and identity. All ten proofs
hold at `Status.VERIFIED`, and the CI job `self-proof` asserts this on every
commit. If a translator regression breaks any self-proof, the job fails before
merge.

This is not a proof of provably's completeness. It is a meaningful invariant:
the translator can correctly handle the constructs it uses in its own core
abstractions.
