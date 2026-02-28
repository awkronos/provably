# Refinement Types

Embed constraints in `typing.Annotated` signatures. provably extracts markers
and adds them as Z3 precondition assumptions automatically.

## Markers

All markers live in `provably.types`.

### `Gt(bound)` -- $x > \text{bound}$

```python
from typing import Annotated
from provably.types import Gt

def f(x: Annotated[float, Gt(0)]) -> float: ...   # x > 0
```

### `Ge(bound)` -- $x \geq \text{bound}$

```python
def f(x: Annotated[float, Ge(0)]) -> float: ...   # x >= 0
```

### `Lt(bound)` -- $x < \text{bound}$

```python
def f(x: Annotated[float, Lt(1)]) -> float: ...   # x < 1
```

### `Le(bound)` -- $x \leq \text{bound}$

```python
def f(x: Annotated[float, Le(100)]) -> float: ...  # x <= 100
```

### `Between(lo, hi)` -- $\text{lo} \leq x \leq \text{hi}$

```python
def f(x: Annotated[float, Between(0, 1)]) -> float: ...   # 0 <= x <= 1
def g(n: Annotated[int,   Between(1, 100)]) -> int: ...   # 1 <= n <= 100
```

### `NotEq(val)` -- $x \neq \text{val}$

```python
def safe_div(x: float, y: Annotated[float, NotEq(0)]) -> float:
    return x / y   # y != 0 guaranteed
```

### Callable markers

Any callable where `m(var)` returns a `z3.BoolRef`:

```python
def is_even(v):
    return v % 2 == 0

@verified(post=lambda n, result: result % 2 == 0)
def double(n: Annotated[int, is_even]) -> int:
    return n * 2
# double.__proof__.verified -> True
```

## Composing markers

Multiple markers on the same parameter are ANDed:

```python
x: Annotated[float, Gt(0), Le(100)]           # 0 < x <= 100
n: Annotated[int, Between(1, 99), NotEq(50)]  # 1 <= n <= 99, n != 50
```

## Convenience aliases

| Alias | Expands to | Meaning |
|---|---|---|
| `Positive` | `Annotated[float, Gt(0)]` | $x > 0$ |
| `NonNegative` | `Annotated[float, Ge(0)]` | $x \geq 0$ |
| `UnitInterval` | `Annotated[float, Between(0, 1)]` | $0 \leq x \leq 1$ |

```python
from provably.types import Positive, NonNegative, UnitInterval

@verified(post=lambda p, q, result: result >= 0)
def blend(p: UnitInterval, q: UnitInterval) -> NonNegative:
    return p * q + (1 - p) * (1 - q)
# blend.__proof__.verified -> True
```

Aliases compose via `Annotated`:

```python
SmallPositive = Annotated[Positive, Le(1)]  # 0 < x <= 1
```

## How provably uses refinements

`extract_refinements(annotation, z3_var)` converts markers to `z3.BoolRef` constraints,
added to the solver before the precondition lambda:

```python
import z3
from provably.types import extract_refinements, Between

x = z3.Real('x')
constraints = extract_refinements(Annotated[float, Between(0, 1)], x)
# [x >= 0.0, x <= 1.0]
```

## Return type annotations

provably extracts return type refinements into postconditions automatically.
A return annotation like `-> Annotated[float, Between(0, 1)]` becomes a proof
obligation just like an explicit `post=`:

```python
@verified()
def clamp01(x: float) -> Annotated[float, Between(0, 1)]:
    if x < 0.0: return 0.0
    if x > 1.0: return 1.0
    return x
# clamp01.__proof__.verified -> True (return type refinement is proven)
```

You can combine return annotations with an explicit `post=` -- both are checked.

## Type checker compatibility

All markers are plain Python objects. `Annotated[float, Ge(0)]` passes through mypy
and pyright without errors -- they see it as `float`.
