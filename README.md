# provably

**Z3-backed formal verification for Python -- via decorators and refinement types**

[![PyPI version](https://img.shields.io/pypi/v/provably?color=gold&labelColor=0a0a0f)](https://pypi.org/project/provably/)
[![Python versions](https://img.shields.io/pypi/pyversions/provably?labelColor=0a0a0f)](https://pypi.org/project/provably/)
[![License](https://img.shields.io/badge/license-MIT-green?labelColor=0a0a0f)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/awkronos/provably/ci.yml?label=CI&labelColor=0a0a0f)](https://github.com/awkronos/provably/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-99%25-brightgreen?labelColor=0a0a0f)](https://github.com/awkronos/provably/actions/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/types-mypy%20strict-blue?labelColor=0a0a0f)](https://mypy.readthedocs.io/)
[![Docs](https://img.shields.io/badge/docs-awkronos.github.io-blue?labelColor=0a0a0f)](https://awkronos.github.io/provably/)

---

```python
from provably import verified

@verified(
    pre=lambda val, lo, hi: lo <= hi,
    post=lambda val, lo, hi, result: (result >= lo) & (result <= hi),
)
def clamp(val: float, lo: float, hi: float) -> float:
    if val < lo:
        return lo
    elif val > hi:
        return hi
    else:
        return val

clamp.__proof__.verified   # True — for ALL inputs where lo <= hi
str(clamp.__proof__)       # "[Q.E.D.] clamp"
```

`verified=True` is a mathematical proof. Z3 determined that **no input** satisfying
the precondition can violate the postcondition.

## Install

```bash
pip install provably
# or: uv add provably
```

## Examples

### Pre/post contracts

```python
@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b

modulo.__proof__.verified        # True
modulo.__proof__.solver_time_ms  # ~2ms
```

### Refinement types

```python
from typing import Annotated
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
@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result * result == n,  # wrong
)
def bad_sqrt(n: int) -> int:
    return n // 2

bad_sqrt.__proof__.counterexample  # {'n': 3, '__return__': 1}
```

### Compositionality

```python
@verified(
    contracts={"my_abs": my_abs.__contract__},
    post=lambda x, y, result: result >= 0,
)
def manhattan(x: float, y: float) -> float:
    return my_abs(x) + my_abs(y)

manhattan.__proof__.verified  # True
```

## Supported constructs

| Construct | Supported |
|---|---|
| `+`, `-`, `*`, `//`, `/`, `%`, `**n` | Yes |
| `<`, `<=`, `>`, `>=`, `==`, `!=` | Yes |
| `and`, `or`, `not`, `&`, `\|`, `~` | Yes |
| `if`/`elif`/`else`/ternary | Yes |
| `min`, `max`, `abs` | Yes |
| `Annotated` refinement types | Yes |
| Calls via `contracts=` | Yes |
| `while` loops, unbounded `for` | No |
| `for i in range(N)` (literal N, max 256) | Yes (unrolled) |
| Recursion | No |
| `str`, `list`, `dict` | No |

## Comparison

| Library | Approach | Proof strength | Call-site overhead |
|---|---|---|---|
| **provably** | SMT / Z3 | Mathematical proof | Zero solver overhead |
| `deal` | Runtime contracts | Bug finding | Per-call |
| `icontract` | Runtime contracts | Bug finding | Per-call |
| `CrossHair` | Symbolic execution | Property testing | Test-time |
| `beartype` | Runtime types | Type checking | Per-call |

## Links

- [Documentation](https://awkronos.github.io/provably/)
- [Getting started](https://awkronos.github.io/provably/getting-started/)
- [How it works](https://awkronos.github.io/provably/concepts/how-it-works/)
- [Self-proof](https://awkronos.github.io/provably/self-proof/)
- [API reference](https://awkronos.github.io/provably/api/decorators/)
- [Changelog](CHANGELOG.md) | [License](LICENSE) (MIT)
