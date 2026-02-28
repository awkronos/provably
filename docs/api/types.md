# provably.types

Refinement type markers and Z3 sort utilities.

```python
from provably.types import (
    Gt, Ge, Lt, Le, Between, NotEq,
    Positive, NonNegative, UnitInterval,
    extract_refinements,
    python_type_to_z3_sort,
    make_z3_var,
)
```

---

## Refinement markers

Use with `typing.Annotated` to embed constraints in function signatures.

### `Gt(bound)`

Strictly greater than `bound`. Generates constraint $x > \text{bound}$.

```python
x: Annotated[float, Gt(0)]    # x > 0
```

### `Ge(bound)`

Greater than or equal to `bound`. Generates constraint $x \geq \text{bound}$.

```python
x: Annotated[float, Ge(0)]    # x >= 0
```

### `Lt(bound)`

Strictly less than `bound`. Generates constraint $x < \text{bound}$.

```python
x: Annotated[float, Lt(1)]    # x < 1
```

### `Le(bound)`

Less than or equal to `bound`. Generates constraint $x \leq \text{bound}$.

```python
x: Annotated[float, Le(100)]  # x <= 100
```

### `Between(lo, hi)`

Inclusive range. Generates constraints $x \geq \text{lo}$ and $x \leq \text{hi}$.

```python
x: Annotated[float, Between(0, 1)]   # 0 <= x <= 1
n: Annotated[int,   Between(1, 100)] # 1 <= n <= 100
```

### `NotEq(val)`

Not equal to `val`. Generates constraint $x \neq \text{val}$.

```python
d: Annotated[float, NotEq(0)]  # d != 0  (safe as divisor)
```

---

## Convenience aliases

Pre-built `Annotated` types for common numeric domains.

### `Positive`

```python
Positive = Annotated[float, Gt(0)]
```

Float strictly greater than zero.

### `NonNegative`

```python
NonNegative = Annotated[float, Ge(0)]
```

Float greater than or equal to zero.

### `UnitInterval`

```python
UnitInterval = Annotated[float, Between(0, 1)]
```

Float in the closed unit interval $[0, 1]$.

---

## `extract_refinements(typ, var)`

```python
extract_refinements(typ: type, var: Any) -> list[Any]
```

Convert `Annotated` type markers into Z3 `BoolRef` constraints for a given symbolic variable.

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `typ` | `type` | A Python type, typically `Annotated[base, *markers]`. |
| `var` | `z3.ExprRef` | The Z3 symbolic variable to constrain. |

### Returns

`list[z3.BoolRef]` — one constraint per marker. Empty if `z3-solver` is not installed
or if `typ` is not `Annotated`.

### Example

```python
import z3
from typing import Annotated
from provably.types import extract_refinements, Between

x = z3.Real('x')
constraints = extract_refinements(Annotated[float, Between(0, 1)], x)
# [x >= 0, x <= 1]
```

### Callable markers

If a marker is callable and `marker(var)` returns a `z3.BoolRef`, it is included:

```python
def is_even(v):
    return v % 2 == 0

constraints = extract_refinements(Annotated[int, is_even], z3.Int('n'))
# [n % 2 == 0]
```

---

## `python_type_to_z3_sort(typ)`

```python
python_type_to_z3_sort(typ: type) -> z3.SortRef
```

Map a Python type annotation to the corresponding Z3 sort.

Strips `Annotated` wrappers before mapping.

| Python type | Z3 sort |
|---|---|
| `int` | `z3.IntSort()` |
| `float` | `z3.RealSort()` |
| `bool` | `z3.BoolSort()` |

Raises `TypeError` for unsupported types. Raises `RuntimeError` if `z3-solver` is not installed.

---

## `make_z3_var(name, typ)`

```python
make_z3_var(name: str, typ: type) -> z3.ExprRef
```

Create a named Z3 symbolic variable from a Python type annotation.

```python
import z3
from provably.types import make_z3_var

x = make_z3_var('x', float)   # z3.Real('x')
n = make_z3_var('n', int)     # z3.Int('n')
b = make_z3_var('b', bool)    # z3.Bool('b')
```

::: provably.types
