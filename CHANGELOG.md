# Changelog

## 0.3.0 (2026-02-28)

### While loops

- Bounded `while` loops now supported, unrolled up to 256 iterations (same limit as `for` loops)
- Optional `# variant: expr` comment for documentation; loops without a termination proof are still unrolled
- Early `return` inside while-loops is handled (remaining iterations skipped with a warning)

### Walrus operator

- `:=` (named expressions / walrus operator) supported in all expression contexts
- Inline assignments bind the variable in the enclosing scope for subsequent Z3 constraints

### Match/case (Python 3.10+)

- `match`/`case` statements desugared to `if`/`elif`/`else` chains for Z3 translation
- Supported patterns: literal values (`MatchValue`), singletons (`MatchSingleton`), and wildcard (`case _:`)
- Guard clauses (`case X if cond:`) supported
- Unsupported patterns (e.g., structural, star, class) raise `TranslationError`

### Tuple returns

- `return (a, b, ...)` encoded as Z3 datatype with uninterpreted accessor functions
- Each tuple element gets a unique `__tuple_N_get_i` accessor bound by axioms
- Tuple unpacking in assignments (`x, y = func(...)`) supported

### Constant subscript

- `arr[0]`, `arr[1]`, etc. supported for tuple-typed expressions
- Only integer literal indices allowed; non-constant subscripts raise `TranslationError`

### New builtins

- `pow(base, exp)` — constant integer exponents 0-3 (same as `**`)
- `bool(x)` — nonzero/nonfalse test (identity for bool, `!= 0` for int/real)
- `int(x)` — identity for int, `ToInt` for real, `If` for bool
- `float(x)` — identity for real, `ToReal` for int, `If` for bool
- `len(x)` — returns an uninterpreted non-negative integer (`len(x) >= 0` axiom added)
- `round(x)` — maps to `ToInt` for real, identity for int

### Lean4 backend

- `verify_with_lean4(func, pre=, post=)` — verify using Lean4 type checker instead of (or alongside) Z3
- `export_lean4(func, pre=, post=, output_path=)` — export a `@verified` function as a Lean4 theorem file
- `HAS_LEAN4` / `LEAN4_VERSION` — runtime detection of Lean4 installation
- Translates Python AST to Lean4 syntax (arithmetic, comparisons, if/elif/else, let bindings)
- Generates `noncomputable def` + `theorem ... := by unfold; split_ifs <;> nlinarith`
- Graceful degradation: returns `SKIPPED` certificate when Lean4 is not installed

### Other improvements

- `assert` statements translated to Z3 proof obligations
- Augmented assignments (`+=`, `-=`, `*=`, etc.) fully supported
- Chained comparisons (`a <= b <= c`) fully supported
- `math.pi` and `math.e` attribute access supported
- `sum()`, `any()`, `all()` builtins supported

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
