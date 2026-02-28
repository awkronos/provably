# provably.types

Refinement type markers and Z3 sort utilities.

```python
from provably.types import (
    Gt, Ge, Lt, Le, Between, NotEq,
    Positive, NonNegative, UnitInterval,
    extract_refinements, python_type_to_z3_sort, make_z3_var,
)
```

---

## Markers

Use with `typing.Annotated` to embed constraints in signatures.

| Marker | Constraint | Example |
|---|---|---|
| `Gt(bound)` | $x > \text{bound}$ | `Annotated[float, Gt(0)]` |
| `Ge(bound)` | $x \geq \text{bound}$ | `Annotated[float, Ge(0)]` |
| `Lt(bound)` | $x < \text{bound}$ | `Annotated[float, Lt(1)]` |
| `Le(bound)` | $x \leq \text{bound}$ | `Annotated[float, Le(100)]` |
| `Between(lo, hi)` | $\text{lo} \leq x \leq \text{hi}$ | `Annotated[float, Between(0, 1)]` |
| `NotEq(val)` | $x \neq \text{val}$ | `Annotated[float, NotEq(0)]` |

Multiple markers on the same parameter are ANDed. Any callable `m(var) -> z3.BoolRef`
is also accepted.

---

## Convenience aliases

| Alias | Definition |
|---|---|
| `Positive` | `Annotated[float, Gt(0)]` |
| `NonNegative` | `Annotated[float, Ge(0)]` |
| `UnitInterval` | `Annotated[float, Between(0, 1)]` |

---

## `extract_refinements(typ, var)`

Convert `Annotated` markers to Z3 constraints for a symbolic variable.

```python
import z3
from provably.types import extract_refinements, Between

x = z3.Real('x')
extract_refinements(Annotated[float, Between(0, 1)], x)
# [x >= 0, x <= 1]
```

---

## `python_type_to_z3_sort(typ)`

| Python type | Z3 sort |
|---|---|
| `int` | `z3.IntSort()` |
| `float` | `z3.RealSort()` |
| `bool` | `z3.BoolSort()` |

Strips `Annotated` wrappers. Raises `TypeError` for unsupported types.

---

## `make_z3_var(name, typ)`

```python
make_z3_var('x', float)  # z3.Real('x')
make_z3_var('n', int)    # z3.Int('n')
make_z3_var('b', bool)   # z3.Bool('b')
```

---

::: provably.types
