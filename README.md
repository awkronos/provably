# provably

**Z3-backed formal verification for Python -- via decorators and refinement types**

[![PyPI](https://img.shields.io/pypi/v/provably)](https://pypi.org/project/provably/)
[![Python](https://img.shields.io/pypi/pyversions/provably)](https://pypi.org/project/provably/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/awkronos/provably/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/awkronos/provably/ci.yml?label=CI)](https://github.com/awkronos/provably/actions/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/types-mypy%20strict-blue)](https://github.com/awkronos/provably)
[![Docs](https://img.shields.io/badge/docs-awkronos.github.io-blue)](https://awkronos.github.io/provably/)

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

### While loops

Bounded `while` loops are unrolled (up to 256 iterations), just like `for` loops:

```python
@verified(
    pre=lambda n: (n >= 0) & (n <= 10),
    post=lambda n, result: result == n * (n + 1) // 2,
)
def triangle(n: int) -> int:
    total = 0
    i = 0
    while i < n:  # variant: n - i
        i += 1
        total += i
    return total

triangle.__proof__.verified  # True
```

### Walrus operator

The walrus operator (`:=`) is supported for inline assignments:

```python
@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)),
)
def my_abs(x: float) -> float:
    return (neg := -x) if x < 0 else x

my_abs.__proof__.verified  # True
```

### Match/case (Python 3.10+)

`match`/`case` statements are desugared to `if`/`elif`/`else` for Z3:

```python
@verified(
    pre=lambda code: (code >= 0) & (code <= 3),
    post=lambda code, result: (result >= 10) & (result <= 40),
)
def dispatch(code: int) -> int:
    match code:
        case 0: return 10
        case 1: return 20
        case 2: return 30
        case _: return 40

dispatch.__proof__.verified  # True
```

### Tuple returns

Functions can return tuples. Each element is accessible via constant subscript:

```python
@verified(
    post=lambda x, y, result: result >= 0,
)
def sum_and_diff(x: float, y: float) -> tuple:
    return (x + y, x - y)
```

### Lean4 backend

Cross-check Z3 results with an independent proof assistant:

```python
from provably import verify_with_lean4, export_lean4

# Verify with Lean4 type checker (requires Lean4 installed)
cert = verify_with_lean4(clamp, pre=lambda v, lo, hi: lo <= hi,
                         post=lambda v, lo, hi, r: (r >= lo) & (r <= hi))

# Export as .lean theorem file
lean_code = export_lean4(clamp, output_path="clamp.lean")
```

## Supported constructs

| Construct | Supported |
|---|---|
| `+`, `-`, `*`, `//`, `/`, `%`, `**n` | Yes |
| `<`, `<=`, `>`, `>=`, `==`, `!=` | Yes |
| `and`, `or`, `not`, `&`, `\|`, `~` | Yes |
| `if`/`elif`/`else`/ternary | Yes |
| `match`/`case` (Python 3.10+) | Yes (desugared to if/elif/else) |
| `min`, `max`, `abs` | Yes |
| `pow`, `bool`, `int`, `float`, `len`, `round` | Yes |
| `sum`, `any`, `all` | Yes |
| `Annotated` refinement types | Yes |
| Calls via `contracts=` | Yes |
| Walrus operator (`:=`) | Yes |
| Tuple returns + constant subscript (`t[0]`) | Yes |
| `while` loops (bounded, max 256 iterations) | Yes (unrolled) |
| `for i in range(N)` (literal N, max 256) | Yes (unrolled) |
| `assert` statements | Yes (become proof obligations) |
| Lean4 backend (`verify_with_lean4`) | Yes (requires Lean4) |
| Recursion | No |
| `str`, `list`, `dict` | No |
| Unbounded loops, generators, async | No |

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
