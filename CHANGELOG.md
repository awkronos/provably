# Changelog

## 0.2.0 (2026-02-28)

### Hypothesis bridge (`provably[hypothesis]`)

- `from_refinements()` — build a Hypothesis strategy from `Annotated` refinement markers
- `from_counterexample()` — replay a Z3 counterexample as a Hypothesis example
- `hypothesis_check()` — run a Hypothesis property test against a `@verified` contract
- `@proven_property` — decorator that registers a Hypothesis test backed by a `ProofCertificate`

### pytest plugin

- `--provably-report` — print a per-module proof summary table at the end of the test run
- `@pytest.mark.proven` — skip the test body if the attached `ProofCertificate` is `VERIFIED`

### ProofCertificate

- `.explain()` — human-readable multi-line description of the verification result
- `.to_prompt()` — single-paragraph LLM-friendly repair message for counterexamples

### Soundness fixes (6)

- Unsupported constructs now raise `TranslationError` instead of being silently skipped
- Composition obligations validated: `contracts=` keys must match call sites in the body
- Cache keys now include contract bytecode hash (source hash alone was insufficient)
- `**n` exponentiation raises `TranslationError` for non-literal or out-of-range `n`
- `for i in range(N)` raises `TranslationError` when `N` exceeds 256 or is non-literal
- Precondition arity mismatch now raises `ContractViolationError` at decoration time

### Self-verification (renamed from "strange loop")

- 10 self-verified functions, all `VERIFIED` on every CI push
- 6 postconditions strengthened: selectivity / passthrough invariants added to `_z3_min`, `_z3_max`, `_z3_abs`, `clamp`, `relu`, `max_of_abs`

### Disk cache

- Proof certificates persisted to `~/.provably/cache/` (SQLite, keyed by source+contract hash)
- `clear_cache()` removes both in-process and disk caches
- Cache survives interpreter restarts; re-import returns the stored certificate instantly

### Documentation

- 37% word reduction across all pages
- 10 false claims corrected (float/real distinction, termination, side effects, compositionality limits)
- "Strange loop" terminology replaced with "self-verification" throughout

## 0.1.0 (2026-02-28)

Initial release.

- `@verified` decorator for Z3-backed formal verification of Python functions
- Refinement types via `typing.Annotated` (`Ge`, `Le`, `Gt`, `Lt`, `Between`, `NotEq`)
- Python AST → Z3 translator supporting arithmetic, comparisons, if/elif/else, early returns, min/max/abs
- Bounded `for i in range(N)` loop unrolling (N must be a compile-time constant)
- Proof certificates attached to functions as `func.__proof__`
- `ProofCertificate.to_json()` / `from_json()` for serialization
- Module-level constant resolution from function globals
- Compositionality via `contracts=` parameter
- `@runtime_checked` decorator for pre/post contract checking without Z3
- `verify_module()` for batch verification of all `@verified` functions in a module
- `configure()` for global settings (timeout, raise_on_failure, log_level)
- Convenience type aliases: `Positive`, `NonNegative`, `UnitInterval`
- Deprecated `strict=` parameter on `@verified`; replaced by `raise_on_failure=`
- Graceful handling of async functions (attach SKIPPED cert, no crash)
- Contract arity validation with actionable error messages
- Line number information in `TranslationError` messages
- `z3-solver` is a required dependency, installed automatically with `pip install provably`
