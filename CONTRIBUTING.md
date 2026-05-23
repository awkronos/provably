# Contributing to provably

provably is small on purpose. Contributions land cleanest when they keep
that property: one tight idea per PR, real test coverage, no scope creep.

## What we accept

In rough priority order:

1. **Translator fixes** for Python constructs that round-trip wrong from
   Z3 (incorrect encoding, missing axioms, soundness gaps). These ship
   fast.
2. **New constructs** (loops, comprehensions, builtins) — must come with
   pytest cases AND an example proving the postcondition holds.
3. **Z3 dialect / solver-backend** improvements (timeouts, tactic
   composition, model retrieval).
4. **Better counter-example presentation.** When verification fails,
   surfacing a concrete input that breaks the postcondition is the
   feature.
5. **Performance work**, backed by `make bench` numbers before/after.
6. **Docs, examples, mkdocs site.**

What we don't accept without a strong case:

- Type-system features beyond plain refinement (no rank-N, no GADTs).
- New solver backends (CVC5, Yices, etc) unless there's a real use
  case Z3 can't cover.
- General-purpose code quality / refactoring PRs without a specific bug.
- Anything that adds dependencies. The promise is `pip install
  provably` and you have a verifier.

## Setup

```bash
git clone https://github.com/awkronos/provably
cd provably
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
make test         # pytest tests/ — should pass clean
make typecheck    # mypy src/provably — strict
make lint         # ruff check src/ tests/
```

`z3-solver>=4.12` is the one hard dependency. Install via pip
(`pip install z3-solver`) — Python wheels exist for macOS / Linux /
Windows arm64+x86_64. No system Z3 needed.

## Soundness mandate

provably exists because `@verified=True` is supposed to mean *mathematical*
verification. Every translator change must preserve that. Concretely:

- **No silent translation loss.** If a Python construct can't be encoded
  losslessly, raise `TranslationError` (or downgrade to `unknown`) —
  never claim verification for code the translator pruned.
- **Every new construct gets a "this breaks if encoding is wrong" test.**
  See `tests/test_loops.py` for the shape: write a function whose
  postcondition is true ONLY IF the construct is encoded correctly, and
  one whose postcondition is false ONLY IF encoded correctly. Both must
  return the expected `verified` value.
- **`make test` MUST be green on the PR branch before review.** No
  "fix lint in follow-up" — that's where bugs hide.

If a PR weakens soundness, it gets reverted regardless of how clever
the diff is.

## Adding a new construct

Workflow that's worked for `while`, `walrus`, `match/case`, tuple
returns:

1. Open an issue or RFC describing the construct + the proposed Z3
   encoding.
2. Add an `ast.<NodeType>` handler in `src/provably/translator.py`. If
   the encoding involves axioms (e.g. `len(x) >= 0`), add them
   alongside the constraint emission.
3. Add **at least three tests** in a new `tests/test_<construct>.py`:
   - One that should `verified=True` and proves it.
   - One that should `verified=False` and the counter-example is the
     specific input that breaks it.
   - One unsupported subcase that raises `TranslationError` with the
     right message.
4. Add an example to `examples/` if the construct is user-facing.
5. Update `CHANGELOG.md` under the next minor version (currently
   `[Unreleased]`).
6. `make test && make typecheck && make lint` clean.
7. PR title: `feat(translator): support <thing>` or `fix(translator):
   <bug>`.

## Performance work

The `make bench` target runs `scripts/sota_bench.py` — 30 representative
contracts timed against the current commit. If your PR touches the
translator or the engine, run `make bench-sota > before.txt` on `main`
and `> after.txt` on your branch, and include the delta in the PR body.

Acceptable: ≤10% regression on individual contracts if the geometric
mean is flat or better. Unacceptable: any individual contract regressing
by >2× without a strong reason.

## Reporting bugs

Best bug report we've gotten: a 12-line `@verified` function, a one-line
description of what should be verified, and "provably says `unknown`
in 30s, here's the `__proof__.smt2` it generated." Include `provably
--version`, Python version, OS, and the contract.

`__proof__.smt2` is what Z3 saw. If we can reproduce the unknown from
that, we can usually fix it the same day.

## Code style

- mypy strict; no `Any`, no untyped public functions.
- ruff defaults (see `pyproject.toml`).
- Module size: prefer 200-500 lines. `translator.py` is the exception
  because the dispatch on `ast.NodeType` can't be cleanly split without
  losing the visitor pattern.
- Internal naming: `_underscore` for module-private; no `__dunder__`
  except magic methods.
- Tests: one assertion per concept. Multiple proof outcomes from one
  contract = multiple test functions.

## Releases

Versioning: SemVer. 0.x is pre-1.0; minor bumps for new constructs,
patch for bug fixes. CHANGELOG.md is the single source of truth; the
release tag matches the topmost version section.

Tim cuts releases. Reach out via the awkronos channel if your PR is
gated on a release.

## Provenance

This library uses git-strict provenance. Every commit must build clean
on the CI workflow. `--no-verify` is forbidden except when a hook is
itself broken; in that case fix the hook in the same PR.

## License

MIT. Contributions are accepted under the same license. By submitting a
PR you confirm you have rights to the code you're contributing.
