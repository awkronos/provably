# Refinement Types

Refinement types let you embed constraints directly in function signatures using
`typing.Annotated`. provably extracts these markers and adds them as precondition
assumptions — no separate `pre=` lambda required for parameter-level constraints.

## Markers

All markers live in `provably.types`.

### `Gt(bound)` — strictly greater than

$$x > \text{bound}$$

```python
from typing import Annotated
from provably.types import Gt

def f(x: Annotated[float, Gt(0)]) -> float: ...   # x > 0
```

### `Ge(bound)` — greater than or equal to

$$x \geq \text{bound}$$

```python
from provably.types import Ge

def f(x: Annotated[float, Ge(0)]) -> float: ...   # x >= 0
```

### `Lt(bound)` — strictly less than

$$x < \text{bound}$$

```python
from provably.types import Lt

def f(x: Annotated[float, Lt(1)]) -> float: ...   # x < 1
```

### `Le(bound)` — less than or equal to

$$x \leq \text{bound}$$

```python
from provably.types import Le

def f(x: Annotated[float, Le(100)]) -> float: ...  # x <= 100
```

### `Between(lo, hi)` — inclusive range

$$\text{lo} \leq x \leq \text{hi}$$

```python
from provably.types import Between

def f(x: Annotated[float, Between(0, 1)]) -> float: ...   # 0 <= x <= 1
def g(n: Annotated[int,   Between(1, 100)]) -> int: ...   # 1 <= n <= 100
```

### `NotEq(val)` — not equal to a value

$$x \neq \text{val}$$

```python
from provably.types import NotEq

def safe_div(x: float, y: Annotated[float, NotEq(0)]) -> float:
    return x / y   # y != 0 is now a precondition; division is safe
```

### Callable markers

Any callable `m` such that `m(var)` returns a `z3.BoolRef` is also accepted:

```python
import z3
from provably import verified

def is_even(v):
    return v % 2 == 0   # works if v is a z3.Int

@verified(post=lambda n, result: result % 2 == 0)
def double(n: Annotated[int, is_even]) -> int:
    return n * 2
# double.__proof__.verified → True
```

## Composing markers

Multiple markers on the same parameter are ANDed together:

```python
# 0 < x <= 100
x: Annotated[float, Gt(0), Le(100)]

# 1 <= n <= 99 and n != 50
n: Annotated[int, Between(1, 99), NotEq(50)]
```

## Convenience aliases

Three pre-built aliases are available as module-level constants:

| Alias | Expands to | Meaning |
|---|---|---|
| `Positive` | `Annotated[float, Gt(0)]` | $x > 0$ |
| `NonNegative` | `Annotated[float, Ge(0)]` | $x \geq 0$ |
| `UnitInterval` | `Annotated[float, Between(0, 1)]` | $0 \leq x \leq 1$ |

```python
from provably.types import Positive, NonNegative, UnitInterval

def norm(x: Positive) -> UnitInterval: ...

@verified(post=lambda p, q, result: result >= 0)
def blend(p: UnitInterval, q: UnitInterval) -> NonNegative:
    return p * q + (1 - p) * (1 - q)
# blend.__proof__.verified → True
```

These are `typing.Annotated` types, so they compose:

```python
from typing import Annotated
from provably.types import Positive, Le

# 0 < x <= 1
SmallPositive = Annotated[Positive, Le(1)]
```

## How provably uses refinements

When provably sees a parameter annotated with `Annotated[T, *markers]`, it calls
`extract_refinements(annotation, z3_var)` to produce a list of `z3.BoolRef` constraints.
These are added to the solver before the precondition lambda, acting as background
assumptions for all proofs involving that function.

`extract_refinements` is public API — you can call it directly if you are building
tooling on top of provably:

```python
import z3
from typing import Annotated
from provably.types import extract_refinements, Between

x = z3.Real('x')
constraints = extract_refinements(Annotated[float, Between(0, 1)], x)
# [x >= 0.0, x <= 1.0]
```

## Refinements on return types

You can annotate the return type with refinement markers. provably does **not** currently
extract these automatically into the postcondition (use `post=` for that), but the
annotations document intent precisely and are readable by other tools:

```python
@verified(post=lambda x, result: (0.0 <= result) & (result <= 1.0))
def clamp01(x: float) -> Annotated[float, Between(0, 1)]:
    if x < 0.0: return 0.0
    if x > 1.0: return 1.0
    return x
# clamp01.__proof__.verified → True
```

## Type checker compatibility

All markers are plain Python objects. `Annotated[float, Ge(0)]` is valid `typing.Annotated`
syntax and passes through mypy, pyright, and beartype without errors. The markers are
ignored by type checkers — they are not `typing` protocol objects — so there is no conflict.
