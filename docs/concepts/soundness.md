# Soundness

What "proven" means, where the trust boundaries lie, and what provably does **not** guarantee.

## What "proven" means

When `func.__proof__.verified == True`:

> For every assignment of values to the function's parameters satisfying the precondition,
> the body -- as translated by provably's AST translator -- satisfies the postcondition.

Formally:

$$\models\; P(\bar{x}) \;\Rightarrow\; Q\!\bigl(\bar{x},\, F(\bar{x})\bigr)$$

Z3 checks $P(\bar{x}) \land \neg Q(\bar{x}, \mathit{ret})$. If no model exists (`unsat`),
the VC is valid.

## The Trusted Computing Base

| Component | Trust basis |
|---|---|
| **Z3** | Microsoft Research. Widely used in formal methods, hardware verification. |
| **`Translator`** (~500 LOC) | provably's own code. A bug here = unsound proof. |
| **`extract_refinements`** | `Annotated` markers &rarr; Z3 constraints. Small, tested. |
| **`python_type_to_z3_sort`** | `int`/`float`/`bool` &rarr; Z3 sorts. Trivial. |
| **Python `ast`** | Standard library. Trusted. |
| **`inspect.getsource`** | Standard library. Caveat: source must match running bytecode. |

Everything outside the TCB -- decorator wrapper, `ProofCertificate`, caching,
`verify_module`, `@runtime_checked` -- cannot produce a spurious `verified=True`.

!!! proof "Self-verification"
    The [self-verification tests](../self-proof.md) exercise the TCB on functions it will later
    verify. Translator regressions are caught before merge.

## Epistemological tiers

| Claim | Tier | Basis |
|---|---|---|
| "This VC is unsatisfiable" | **Theorem** | Z3 UNSAT proof |
| "The translator correctly encodes Python" | **Tested claim** | Unit tests on TCB |
| "Z3 is sound" | **Trusted external theorem** | Published soundness proofs |
| "provably covers all Python semantics" | **False** | Only a subset |

## What provably does NOT guarantee

**1. Termination.** Functions that never return satisfy any postcondition vacuously.
provably rejects unbounded loops precisely for this reason.

**2. Unsupported constructs.** Calls to unverified helpers raise `TranslationError`.
provably refuses to silently skip call sites.

**3. Floating-point.** Python `float` is IEEE 754 binary64. Z3's `RealSort` models
exact reals. Proofs over `float` are proofs over the reals. If correctness depends
on specific rounding behavior, the proof may not transfer.

**4. Side effects.** provably reasons about return values only. I/O, global state,
and mutable arguments are unconstrained.

**5. Timeout != false.** `Status.UNKNOWN` means the solver didn't finish -- not that
the contract is wrong.

## Comparison to Coq and Lean

| | provably | Coq / Lean |
|---|---|---|
| Approach | SMT (push-button) | Interactive theorem prover |
| User effort | Decorator + contracts | Proof terms / tactics |
| Kernel | Z3 (external) | Verified kernel (de Bruijn) |
| Expressiveness | Arithmetic, restricted Python | All of dependent type theory |
| Best for | Pre/post on numeric code | Deep correctness, recursion, data structures |

## The core guarantee

!!! theorem "Sound and incomplete"
    provably is **sound** modulo the TCB: if it says `verified`, the VC is valid.
    It is **incomplete**: some valid properties cannot be checked.
    Sound and incomplete beats complete and unsound.
