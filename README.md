# provably

**Proof-carrying Python — Z3-backed formal verification via decorators and refinement types**

[![PyPI version](https://img.shields.io/pypi/v/provably?color=blue)](https://pypi.org/project/provably/)
[![Python versions](https://img.shields.io/pypi/pyversions/provably)](https://pypi.org/project/provably/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/awkronos/provably/actions/workflows/ci.yml/badge.svg)](https://github.com/awkronos/provably/actions/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/types-mypy%20strict-blue)](https://mypy.readthedocs.io/)
[![Docs](https://img.shields.io/badge/docs-awkronos.github.io-blue)](https://awkronos.github.io/provably/)

---

```python
from provably import verified

@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
)
def integer_sqrt(x: int) -> int:
    n = 0
    while (n + 1) * (n + 1) <= x:
        n += 1
    return n

assert integer_sqrt.__proof__.verified  # Q.E.D.
```

## Install

```bash
pip install provably[z3]
```

The `[z3]` extra pulls in `z3-solver`. The base package installs with zero dependencies
and falls back gracefully when Z3 is absent (runtime checking only).

## Examples

### Basic `@verified` — pre/post contracts

```python
from provably import verified

@verified(
    pre=lambda a, b: b != 0,
    post=lambda a, b, result: result * b == a,
)
def exact_divide(a: int, b: int) -> int:
    return a // b

proof = exact_divide.__proof__
print(proof.verified)        # True
print(proof.solver_time_ms)  # e.g. 3.1 (milliseconds)
```

### Refinement types — constraints in signatures

```python
from typing import Annotated
from provably import verified
from provably.types import Ge, Le, Between, NonNegative, UnitInterval

@verified(
    post=lambda p, q, result: result >= 0,
)
def blend(
    p: Annotated[float, Between(0, 1)],
    q: Annotated[float, Ge(0), Le(1)],
) -> NonNegative:
    return p * q + (1 - p) * (1 - q)

# Signature-level constraints are automatically added as precondition assumptions.
assert blend.__proof__.verified
```

### Counterexample extraction — catch bugs before tests do

```python
from provably import verified

@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result >= n,   # BUG: should be result * result >= n
)
def bad_sqrt(n: int) -> int:
    return n // 2

proof = bad_sqrt.__proof__
print(proof.verified)        # False
print(proof.counterexample)  # {'n': 3, '__return__': 1}  — 1 < 3
```

## What it proves

provably translates a **restricted subset of Python** into Z3 constraints and checks that
the verification condition (VC) is unsatisfiable — meaning no input can violate the contract.

| Construct | Supported |
|---|---|
| Arithmetic: `+`, `-`, `*`, `//`, `/`, `**` | Yes |
| Comparisons: `<`, `<=`, `>`, `>=`, `==`, `!=` | Yes |
| Boolean logic: `and`, `or`, `not` | Yes |
| `if` / `elif` / `else` | Yes |
| Early `return` | Yes |
| `min(a, b)`, `max(a, b)`, `abs(x)` | Yes |
| Module-level integer/float constants | Yes |
| Annotated refinement types on parameters | Yes |
| Calls to other `@verified` functions (via `contracts=`) | Yes |
| `while` loops | No — undecidable in general |
| Recursion | No — requires ranking functions |
| String / list / dict operations | No — outside SMT integer/real arithmetic |
| Lambdas, closures, generators | No |

When a construct is unsupported, provably raises `TranslationError` with a precise message
pointing to the offending AST node.

## How it works

provably retrieves the source of the decorated function via `inspect.getsource`, parses it
with Python's `ast` module, and walks the AST to emit Z3 expressions. It then asserts the
negation of the postcondition (under the precondition) and calls `z3.Solver.check()`. If
the result is `unsat`, no counterexample exists — the contract is a mathematical theorem
for all inputs satisfying the precondition. If the result is `sat`, Z3 produces a concrete
model that is a counterexample. If the result is `unknown`, the solver timed out.

## Comparison

| Library | Approach | Proof strength | Runtime overhead |
|---|---|---|---|
| **provably** | SMT / Z3, static | Mathematical proof | Zero (proofs at import time) |
| `deal` | Runtime contracts | Bug finding | Per-call |
| `icontract` | Runtime contracts | Bug finding | Per-call |
| `CrossHair` | Symbolic execution | Property testing | Test-time |
| `beartype` | Runtime types | Type checking | Per-call (fast) |

provably is the only library in this table that produces **proofs** rather than
test witnesses. A `verified=True` result means the property holds for every possible
input satisfying the precondition — not just the inputs you happened to test.

## Links

- [Documentation](https://awkronos.github.io/provably/)
- [Getting started](https://awkronos.github.io/provably/getting-started/)
- [API reference](https://awkronos.github.io/provably/api/decorators/)
- [Changelog](CHANGELOG.md)
- [License](LICENSE) (MIT)
