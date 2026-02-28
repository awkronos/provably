# Contracts

Contracts in provably are Python lambdas passed to `@verified` as `pre` and `post`.

## Syntax

```python
from provably import verified

@verified(
    pre=lambda x, y: ...,               # precondition
    post=lambda x, y, result: ...,      # postcondition
)
def f(x: int, y: int) -> int: ...
```

- `pre` receives the same parameter names as the function, in order.
- `post` receives the same parameter names **plus `result` as the last argument**, bound to
  the symbolic return value.
- Both must return a Z3 boolean expression. The lambda body is passed through the same
  AST pipeline as the function body.

## The `result` convention

`result` is the name provably uses for the return value in postconditions.
It is always the last argument to `post`:

```python
@verified(
    pre=lambda n: n > 0,
    post=lambda n, result: (result > 0) & (result <= n),
)
def collatz_step(n: int) -> int:
    if n % 2 == 0:
        return n // 2
    return 3 * n + 1
```

The name `result` is fixed — do not use a different name.

## `&` / `|` / `~` — not `and` / `or` / `not`

In pre/post lambdas for `@verified`, you must use the bitwise operators `&`, `|`, `~`
for logical AND, OR, NOT. Python's `and` / `or` short-circuit and do **not** produce
Z3 `BoolRef` objects — they will silently return one of their operands as a Python
value, not a Z3 constraint:

```python
# WRONG — 'and' returns the second Z3 expression, not z3.And
post=lambda a, b, result: result >= 0 and result < b

# CORRECT
post=lambda a, b, result: (result >= 0) & (result < b)
```

In `pre` lambdas with numeric comparisons (no Z3 variables yet created), plain `and`
may appear to work, but `&` is always safer and consistent.

For `@runtime_checked`, plain `and` / `or` / `not` work correctly because there are no
Z3 expressions involved.

## Multiple postconditions

Combine with `&` for multiple conditions in a single lambda:

```python
@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b
```

## `pre=None`

Omit `pre` (or set it to `None`) to assert the postcondition unconditionally — for all
possible inputs:

```python
@verified(
    post=lambda x, result: result == abs(x),
)
def my_abs(x: int) -> int:
    return x if x >= 0 else -x
```

## Accessing module-level constants

Lambdas can reference module-level integer and float constants. The engine resolves
free names in the lambda body against the function's global scope and injects them as
concrete Z3 values:

```python
MAX = 100

@verified(
    post=lambda x, result: result <= MAX,
)
def cap(x: int) -> int:
    if x > MAX:
        return MAX
    return x
```

Module-level constants that are not `int` or `float` will result in `TRANSLATION_ERROR`.

## Compositionality via `contracts=`

Pass `contracts=` with a dict of helper function contracts to enable modular verification.
See [Compositionality](compositionality.md) for details.

## Contract limitations

- Contracts are lambdas — single expressions only. Use `&` to combine conditions.
- Contracts cannot contain assignments or `yield`.
- The translator supports the same arithmetic / comparison / boolean subset as the function
  body. See [Supported Python](../guides/supported-python.md).
