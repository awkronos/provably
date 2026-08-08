<div align="center">
  <img src="docs/logo.png" alt="provably" width="180" />

  # provably

  **Z3-backed formal verification for Python — via decorators and refinement types.**

  _An [awkronos](https://awkronos.com) library. The Python sibling of [`provably`](https://crates.io/crates/provably) for Rust._

  [![PyPI](https://img.shields.io/pypi/v/provably?color=D97706)](https://pypi.org/project/provably/)
  [![Python](https://img.shields.io/pypi/pyversions/provably?color=1E1B4B)](https://pypi.org/project/provably/)
  [![CI](https://img.shields.io/github/actions/workflow/status/awkronos/provably/ci.yml?branch=main&logo=github)](https://github.com/awkronos/provably/actions/workflows/ci.yml)
  [![license](https://img.shields.io/pypi/l/provably?color=1E1B4B)](https://github.com/awkronos/provably/blob/main/LICENSE)
  [![typed](https://img.shields.io/badge/types-mypy%20strict-1E1B4B)](https://github.com/awkronos/provably)
  [![awkronos](https://img.shields.io/badge/awkronos-library-1E1B4B?labelColor=FAFAF8)](https://awkronos.com)
  [![docs](https://img.shields.io/badge/docs-awkronos.github.io-1E1B4B)](https://awkronos.github.io/provably/)
</div>

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

bad_sqrt.__proof__.counterexample  # e.g. {'n': 7, '__return__': 3} — 3*3 != 7
# Z3 returns *some* input that breaks the contract; the exact value may vary.
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
    # Use `2 * result == n * (n + 1)`, not `result == n * (n + 1) // 2`:
    # `//` is not defined on Z3 expressions inside a contract lambda.
    post=lambda n, result: 2 * result == n * (n + 1),
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

Subscript the result with a constant index — `result` is a tuple, so a bare
`result >= 0` is a type error:

```python
@verified(
    post=lambda x, y, result: (result[0] == x + y) & (result[1] == x - y),
)
def sum_and_diff(x: float, y: float) -> tuple:
    return (x + y, x - y)

sum_and_diff.__proof__.verified  # True
```

### Lean 4 backend

Cross-check Z3 results with an independent proof assistant:

```python
from provably import verify_with_lean4, export_lean4

cert = verify_with_lean4(clamp, pre=lambda v, lo, hi: lo <= hi,
                         post=lambda v, lo, hi, r: (r >= lo) & (r <= hi))

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
| Lean 4 backend (`verify_with_lean4`) | Yes (requires Lean 4) |
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

## Benchmark

`make bench` proves the same property — ERC-20 transfer overflow safety,
end-to-end — with provably and with real contract-verification tooling
(halmos, pysmt-z3, cvc5, raw z3, solc SMTChecker), then compares wall time.

```bash
make bench          # writes /tmp/kagami-provably-bench.json
# {"actual": ..., "sota": ..., "sota_name": ..., "efficiency_pct": ..., "competitors": [...]}
# efficiency_pct > 100 means provably beat the fastest competitor.
```

## Links

- [Product architecture](ARCHITECTURE.md) — Python ↔ Rust ↔ `pcc-core` ↔ `pcc-sp1`
- [Documentation](https://awkronos.github.io/provably/)
- [Getting started](https://awkronos.github.io/provably/getting-started/)
- [How it works](https://awkronos.github.io/provably/concepts/how-it-works/)
- [Self-proof](https://awkronos.github.io/provably/self-proof/)
- [API reference](https://awkronos.github.io/provably/api/decorators/)
- Sibling crates: [`provably-rs`](../provably-rs) · [`pcc-core`](../pcc-core) · [`pcc-sp1`](../pcc-sp1)
- [Changelog](CHANGELOG.md) · [License](LICENSE) (MIT)

---

<div align="center">

**awkronos** — a small penguin with snow on its head.
We prove the math you've been meaning to do.

[awkronos.com](https://awkronos.com) · [essays](https://tim.awkronos.com)

</div>
