# Contracts

Contracts are Python lambdas passed to `@verified` as `pre` and `post`.

## Syntax

```python
from provably import verified

@verified(
    pre=lambda x, y: ...,               # precondition: same params as function
    post=lambda x, y, result: ...,      # postcondition: params + result
)
def f(x: int, y: int) -> int: ...
```

Both must return a Z3 boolean expression. The lambda body passes through the same AST pipeline as the function body.

## The `result` convention

`result` is always the last argument to `post`, bound to the symbolic return value:

```python
@verified(
    pre=lambda n: n > 0,
    post=lambda n, result: (result > 0) & (result <= n),
)
def collatz_step(n: int) -> int:
    if n % 2 == 0:
        return n // 2
    return 3 * n + 1
# collatz_step.__proof__.verified -> True
```

The name `result` is fixed.

## `&` / `|` / `~` -- not `and` / `or` / `not`

!!! warning "Silent failure mode"
    `result >= 0 and result < b` does not raise an error. It returns `result < b`
    as the entire postcondition, silently dropping `result >= 0`. Always use `&`, `|`, `~`.

```python
# WRONG -- 'and' returns the second operand, dropping the first
post=lambda a, b, result: result >= 0 and result < b

# CORRECT -- & builds z3.And
post=lambda a, b, result: (result >= 0) & (result < b)
```

Parentheses required: `&` has lower precedence than `>=`.

For `@runtime_checked`, plain `and`/`or`/`not` work fine -- no Z3 involved.

## Multiple postconditions

Combine with `&`:

```python
@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result >= 0) & (result < b),
)
def modulo(a: int, b: int) -> int:
    return a % b
# modulo.__proof__.verified -> True
```

## Omitting `pre`

No `pre` (or `pre=None`) asserts the postcondition for **all possible inputs**:

```python
@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)),
)
def my_abs(x: int) -> int:
    return x if x >= 0 else -x
# my_abs.__proof__.verified -> True
```

## Module-level constants

Lambdas can reference module-level `int` and `float` constants:

```python
MAX = 100

@verified(post=lambda x, result: (result <= MAX) & (result >= 0))
def cap(x: int) -> int:
    if x > MAX: return MAX
    if x < 0: return 0
    return x
# cap.__proof__.verified -> True
```

Non-numeric constants produce `TranslationError`.

## Contract strength

Prefer the **strongest** postcondition Z3 can close:

```python
# Weak -- consistent with returning 0 always
post=lambda x, result: result >= 0

# Strong -- complete specification of abs
post=lambda x, result: (result >= 0) & ((result == x) | (result == -x))
```

## Limitations

- Single-expression lambdas only. Combine conditions with `&`.
- No assignments or `yield` in contracts.
- Same arithmetic/comparison/boolean subset as function bodies. See [Supported Python](../guides/supported-python.md).
- For modular verification via `contracts=`, see [Compositionality](compositionality.md).
