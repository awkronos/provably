# provably

**Proof-carrying Python — Z3-backed formal verification via decorators and refinement types**

[![PyPI version](https://img.shields.io/pypi/v/provably?color=gold&labelColor=0a0a0f)](https://pypi.org/project/provably/)
[![Python versions](https://img.shields.io/pypi/pyversions/provably?labelColor=0a0a0f)](https://pypi.org/project/provably/)
[![License](https://img.shields.io/badge/license-MIT-green?labelColor=0a0a0f)](LICENSE)
[![CI](https://github.com/awkronos/provably/actions/workflows/ci.yml/badge.svg)](https://github.com/awkronos/provably/actions/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/types-mypy%20strict-blue?labelColor=0a0a0f)](https://mypy.readthedocs.io/)
[![Docs](https://img.shields.io/badge/docs-awkronos.github.io-blue?labelColor=0a0a0f)](https://awkronos.github.io/provably/)

---

```python
from provably import verified

@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: (result * result <= x) & (x < (result + 1) * (result + 1)),
)
def integer_sqrt(x: int) -> int:
    n = 0
    while (n + 1) * (n + 1) <= x:
        n += 1
    return n

integer_sqrt.__proof__.verified   # True
str(integer_sqrt.__proof__)       # "[Q.E.D.] integer_sqrt"
```

A `verified=True` result is a mathematical proof — not a test, not a sample, not a fuzzer guess.
Z3 determined that **no input** satisfying the precondition can violate the postcondition.

## Install

```bash
pip install provably[z3]
# or: uv add "provably[z3]"
```

The `[z3]` extra pulls in `z3-solver`. The base package has zero dependencies —
`@runtime_checked` works without Z3.

## Examples

### Pre/post contracts

```python
from provably import verified

@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b

modulo.__proof__.verified        # True
modulo.__proof__.solver_time_ms  # ~2 ms
```

### Refinement types

```python
from typing import Annotated
from provably import verified
from provably.types import Between, Gt, NonNegative

@verified(post=lambda p, x, result: result >= 0)
def scale(
    p: Annotated[float, Between(0, 1)],
    x: Annotated[float, Gt(0)],
) -> NonNegative:
    return p * x

scale.__proof__.verified  # True
```

### Counterexample extraction

```python
from provably import verified

@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result * result == n,  # wrong — isqrt ≠ exact square root
)
def bad_sqrt(n: int) -> int:
    return n // 2

bad_sqrt.__proof__.verified       # False
bad_sqrt.__proof__.counterexample # {'n': 3, '__return__': 1}
# 1 * 1 = 1 ≠ 3. Fix the contract, not the function.
```

### Compositionality

```python
@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)),
)
def my_abs(x: float) -> float:
    return x if x >= 0 else -x

@verified(
    contracts={"my_abs": my_abs.__contract__},
    post=lambda x, y, result: result >= 0,
)
def manhattan(x: float, y: float) -> float:
    return my_abs(x) + my_abs(y)  # provably knows my_abs returns >= 0

manhattan.__proof__.verified  # True
```

## What provably proves

| Construct | Supported |
|---|---|
| Arithmetic: `+`, `-`, `*`, `//`, `/`, `%`, `**n` | Yes |
| Comparisons: `<`, `<=`, `>`, `>=`, `==`, `!=` | Yes |
| Boolean: `and`, `or`, `not`, `&`, `\|`, `~` | Yes |
| `if` / `elif` / `else` / ternary | Yes |
| Early `return` | Yes |
| `min(a, b)`, `max(a, b)`, `abs(x)` | Yes |
| Module-level integer/float constants | Yes |
| `Annotated` refinement types | Yes |
| Calls to `@verified` functions (via `contracts=`) | Yes |
| `while` / `for` loops | No — undecidable in general |
| Recursion | No — requires ranking functions |
| `str`, `list`, `dict` operations | No — outside SMT arithmetic |

## Comparison

| Library | Approach | Proof strength | Call-site overhead |
|---|---|---|---|
| **provably** | SMT / Z3, static | Mathematical proof | Zero |
| `deal` | Runtime contracts | Bug finding | Per-call |
| `icontract` | Runtime contracts | Bug finding | Per-call |
| `CrossHair` | Symbolic execution | Property testing | Test-time |
| `beartype` | Runtime types | Type checking | Per-call (fast) |

provably is the only library here that produces **proofs** rather than test witnesses.

## Links

- [Documentation](https://awkronos.github.io/provably/)
- [Getting started](https://awkronos.github.io/provably/getting-started/)
- [How it works](https://awkronos.github.io/provably/concepts/how-it-works/)
- [Self-proof — the strange loop](https://awkronos.github.io/provably/self-proof/)
- [API reference](https://awkronos.github.io/provably/api/decorators/)
- [Changelog](CHANGELOG.md) · [License](LICENSE) (MIT)
