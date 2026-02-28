# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/).

---

## [Unreleased]

### Added

- `@verified` decorator: `pre`, `post`, `contracts`, `timeout_ms`, `raise_on_failure`, `check_contracts`.
- `ProofCertificate`: frozen dataclass with `verified` property, `to_json()`/`from_json()`, counterexample extraction.
- `@runtime_checked`: call-time pre/post checking without Z3. Raises `ContractViolationError`.
- `VerificationError` for `raise_on_failure=True`.
- `verify_module()` and `verify_function()` for programmatic use.
- `configure()`: `timeout_ms`, `raise_on_failure`, `log_level`.
- Refinement types: `Gt`, `Ge`, `Lt`, `Le`, `Between`, `NotEq`.
- Convenience aliases: `Positive`, `NonNegative`, `UnitInterval`.
- `extract_refinements()`, `python_type_to_z3_sort()`, `make_z3_var()`.
- AST `Translator`: arithmetic, comparisons, booleans, `if/elif/else`, early returns, `min`/`max`/`abs`, module constants, `contracts=` compositionality.
- Proof caching by content hash. `clear_cache()`.
- `z3-solver` as required dependency.
- Full type annotations (`py.typed`). Passes mypy strict.
- Python 3.10 / 3.11 / 3.12 / 3.13.

---

*Initial public release. See [GitHub releases](https://github.com/awkronos/provably/releases) for subsequent versions.*
