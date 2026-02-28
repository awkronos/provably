# Changelog

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
