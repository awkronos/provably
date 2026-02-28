# Soundness

provably makes strong claims. This page is precise about what those claims are, where
the trust boundaries lie, and what provably does **not** guarantee.

## What "proven" means

When `func.__proof__.verified == True`, the following statement holds:

> For every assignment of values to the function's parameters satisfying the precondition,
> the body of the function, as translated by provably's AST translator, satisfies the
> postcondition.

This is a **mathematical theorem** in the theory of linear arithmetic (or nonlinear
arithmetic, depending on the constructs used). It is not a test, not a sample, not a
probabilistic bound.

Formally, provably checks that the verification condition (VC) is a tautology:

$$\models\; P(\bar{x}) \;\Rightarrow\; Q\!\bigl(\bar{x},\, F(\bar{x})\bigr)$$

by asking Z3 to find a model of $P(\bar{x}) \land \neg Q(\bar{x}, \mathit{ret})$. If no
model exists (`unsat`), the VC is valid.

## The Trusted Computing Base (TCB)

A proof is only as trustworthy as the components it relies on. The TCB for a provably proof
consists of:

| Component | Trust basis |
|---|---|
| **Z3 SMT solver** | Maintained by Microsoft Research. Widely used in formal methods, hardware verification, security analysis. De Bruijn principle: Z3 can produce proof certificates checkable by independent validators. |
| **`Translator` (AST → Z3)** | provably's own code. Small (~500 LOC), unit-tested for every supported construct. A bug here can produce an unsound proof. |
| **`extract_refinements`** | provably's own code. Converts `Annotated` markers to Z3 constraints. Small, tested. |
| **`python_type_to_z3_sort`** | provably's own code. Maps `int`/`float`/`bool` to Z3 sorts. Trivial. |
| **Python's `ast` module** | Standard library. Trusted. |
| **`inspect.getsource`** | Standard library. **Caveat**: if the source on disk differs from the bytecode in memory (e.g., after hot-reloading), the proof may not match the running code. |

Everything outside the TCB — the `@verified` decorator wrapper, `ProofCertificate`, caching,
`verify_module`, `@runtime_checked` — does not affect soundness. A bug there can produce
incorrect metadata but cannot produce a spurious `verified=True`.

!!! proof "Self-verification"
    provably reduces its translator's blast radius by proving its own core functions.
    The [strange loop](../self-proof.md) means: if the translator has a bug that produces
    a wrong proof for `_z3_min` or `clamp`, the CI self-proof job catches it.
    It cannot catch bugs in untested constructs — but it exercises the core fragment.

## Epistemological tiers

Following the project's epistemology:

| Claim | Tier | Basis |
|---|---|---|
| "This VC is unsatisfiable" | **Theorem** | Z3 UNSAT proof |
| "The translator correctly encodes Python semantics" | **Tested claim** | Unit tests on the TCB. Not formally verified. |
| "Z3 is sound" | **Trusted external theorem** | Published soundness proofs for the SMT-LIB theories Z3 implements |
| "provably covers Python semantics completely" | **False** — only a subset | See [Supported Python](../guides/supported-python.md) |

## What provably does NOT guarantee

**1. Termination.** provably does not verify that functions terminate. A function with
a `while` loop that never exits satisfies any postcondition vacuously by never returning.
provably rejects unbounded `while` loops precisely because termination is undecidable in general.
See the FAQ in [Supported Python](../guides/supported-python.md).

**2. Runtime correctness of unsupported constructs.** If your function calls a non-verified
helper that provably cannot translate, you must list it in `contracts=` with its own proof.
provably refuses to silently skip call sites — it raises `TranslationError`.

**3. Floating-point arithmetic.** Python `float` is IEEE 754 binary64, not mathematical
real arithmetic. Z3's `RealSort` models exact real numbers. A proof that uses `float`
parameters is actually a proof over the reals. If your function's correctness depends on
specific floating-point rounding behavior, the proof may not transfer.

**4. Side effects.** provably only reasons about return values. Functions that write to
global state, I/O, or mutable arguments are not constrained by provably's contracts on
those side channels.

**5. Timeout = unknown, not false.** If Z3 times out, `cert.status == Status.UNKNOWN`.
`cert.verified` is `False`. This means the answer is **unknown** — not that the contract
is wrong. Increase the timeout via `configure(timeout_ms=...)` or simplify the function.

## Comparison to Coq and Lean

| | provably | Coq / Lean |
|---|---|---|
| **Proof approach** | SMT (push-button) | Interactive theorem prover |
| **User effort** | Write a decorator | Write proof terms / tactics |
| **Kernel** | Z3 (external, trusted) | Verified kernel (de Bruijn) |
| **Automation** | Fully automatic | Automation for some goals; manual for others |
| **Expressiveness** | Linear/nonlinear arithmetic, restricted Python subset | All of dependent type theory |
| **Best for** | Pre/post contracts on numeric code | Deep correctness properties, recursive algorithms, data structures |

provably occupies a practical middle ground: it handles a large class of real-world numeric
correctness properties automatically, at the cost of expressiveness and a small trusted
translation layer. For properties that require inductive proofs, loop invariants, or
recursive reasoning, a proof assistant is the appropriate tool.

## Soundness vs. completeness

!!! theorem "The core guarantee"
    provably is **sound** modulo the TCB: if it says `verified`, the VC is valid. It is
    **incomplete**: some valid properties over unsupported constructs cannot be checked.
    This is the correct trade-off for a push-button tool. Sound and incomplete beats
    complete and unsound — a spurious proof is worse than no proof.
