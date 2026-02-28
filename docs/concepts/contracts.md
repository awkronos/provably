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
- Both must return a Z3 boolean expression. The lambda body passes through the same
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

# For any n > 0:
#   result > 0  (always positive)
#   result <= n  (weakens toward fixed point n=1... for most n)
# collatz_step.__proof__.verified → True
```

The name `result` is fixed — do not use a different name.

## `&` / `|` / `~` — not `and` / `or` / `not`

In pre/post lambdas for `@verified`, use the bitwise operators `&`, `|`, `~`
for logical AND, OR, NOT. Python's `and` / `or` short-circuit and do **not** produce
Z3 `BoolRef` objects — they silently return one of their operands as a Python value:

```python
# WRONG — 'and' returns the second Z3 expression, dropping the first conjunct
post=lambda a, b, result: result >= 0 and result < b

# CORRECT — & builds a z3.And expression
post=lambda a, b, result: (result >= 0) & (result < b)
```

!!! warning "Silent failure mode"
    `result >= 0 and result < b` does not raise an error — it returns `result < b`
    as the entire postcondition, silently dropping `result >= 0`. This can produce a
    proof of a weaker contract than intended. Always use `&`, `|`, `~`.

For `@runtime_checked`, plain `and` / `or` / `not` work correctly because there are no
Z3 expressions involved.

## Multiple postconditions

Combine with `&`:

```python
@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b

# result >= 0 AND result < b — both proved simultaneously.
# modulo.__proof__.verified → True
```

## `pre=None`

Omit `pre` (or set it to `None`) to assert the postcondition unconditionally — for all
possible inputs:

```python
@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)),
)
def my_abs(x: int) -> int:
    return x if x >= 0 else -x

# Proves: for ALL integers x (no precondition whatsoever),
# abs returns x or -x and the result is non-negative.
# my_abs.__proof__.verified → True
```

## Accessing module-level constants

Lambdas can reference module-level integer and float constants. The engine resolves
free names in the lambda body against the function's global scope and injects them as
concrete Z3 values:

```python
MAX = 100

@verified(
    post=lambda x, result: (result <= MAX) & (result >= 0),
)
def cap(x: int) -> int:
    if x > MAX:
        return MAX
    if x < 0:
        return 0
    return x

# Proves result is always in [0, 100], for all integer x.
# cap.__proof__.verified → True
```

Module-level constants that are not `int` or `float` will result in `TranslationError`.

## Compositionality via `contracts=`

Pass `contracts=` with a dict of helper function contracts to enable modular verification.
See [Compositionality](compositionality.md) for details.

## Contract strength

Prefer **stronger** postconditions. A weak postcondition that is easy to prove may not
be useful — it allows too many implementations.

```python
# WEAK: proves non-negative — consistent with returning 0 always
post=lambda x, result: result >= 0

# STRONG: proves result equals x or -x — rules out result=0 when x=5
post=lambda x, result: (result >= 0) & ((result == x) | (result == -x))
```

The stronger form is the complete specification of absolute value. If Z3 can close it, use it.

## Contract limitations

- Contracts are single-expression lambdas. Use `&` to combine conditions.
- Contracts cannot contain assignments or `yield`.
- The translator supports the same arithmetic / comparison / boolean subset as the function
  body. See [Supported Python](../guides/supported-python.md).
