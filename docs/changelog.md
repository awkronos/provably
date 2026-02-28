# Changelog

All notable changes to provably are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
provably uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- `@verified` decorator with `pre`, `post`, `contracts`, `timeout_ms`, `raise_on_failure`, `skip` parameters.
- `ProofCertificate` frozen dataclass: `function_name`, `source_hash`, `status`, `preconditions`, `postconditions`, `counterexample`, `message`, `solver_time_ms`, `z3_version`. `.verified` property. `.to_json()` / `.from_json()` serialization.
- `@runtime_checked` decorator for call-time pre/post checking without Z3. Raises `ContractViolationError`.
- `VerificationError` raised by `@verified(raise_on_failure=True)`.
- `verify_module()` for batch collection of proof certificates across a module.
- `verify_function()` low-level entry point for programmatic use.
- `configure()` for global settings: `timeout_ms`, `raise_on_failure`, `log_level`.
- Refinement type markers: `Gt`, `Ge`, `Lt`, `Le`, `Between`, `NotEq`.
- Convenience aliases: `Positive`, `NonNegative`, `UnitInterval`.
- `extract_refinements()`, `python_type_to_z3_sort()`, `make_z3_var()` utilities.
- AST translator (`Translator`) covering: arithmetic, comparisons, boolean logic, `if/elif/else`, early returns, `min`, `max`, `abs`, module-level constants, compositionality via `contracts=`.
- Proof caching by function identity, invalidated via `clear_cache()`.
- Zero mandatory runtime dependencies. `z3-solver` is optional (`pip install provably[z3]`).
- Full type annotations (`py.typed` marker). Passes mypy strict.
- Python 3.11 / 3.12 / 3.13 support.

---

*This is the initial public release. See [GitHub releases](https://github.com/awkronos/provably/releases) for subsequent versions.*
