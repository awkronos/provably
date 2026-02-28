# Supported Python Subset

provably translates a restricted subset of Python into Z3 constraints. This page documents
exactly what is supported, what is not, and why.

## Supported constructs

### Types

| Python type | Z3 sort | Notes |
|---|---|---|
| `int` | `IntSort` | Mathematical integers (unbounded) |
| `float` | `RealSort` | Mathematical reals, not IEEE 754 |
| `bool` | `BoolSort` | `True` / `False` |
| `Annotated[T, *markers]` | Same as `T` | Markers become precondition assumptions |

### Arithmetic operators

| Operator | Z3 encoding | Caveat |
|---|---|---|
| `x + y` | `x + y` | |
| `x - y` | `x - y` | |
| `x * y` | `x * y` | Nonlinear if both symbolic — solver may be slower |
| `x / y` | `x / y` (real) | `y != 0` must be in `pre` or refinement |
| `x // y` | `z3.ToInt(x / y)` | Integer floor division |
| `x % y` | `x - y * z3.ToInt(x / y)` | |
| `x ** n` | `x * x * ...` (n times) | `n` must be a concrete integer literal 0–3 |
| `-x` | `-x` | |
| `+x` | `x` | |

### Comparison operators

| Operator | Z3 encoding |
|---|---|
| `x < y` | `x < y` |
| `x <= y` | `x <= y` |
| `x > y` | `x > y` |
| `x >= y` | `x >= y` |
| `x == y` | `x == y` |
| `x != y` | `x != y` |

Chained comparisons (`0 <= x <= 1`) are supported and desugared to `z3.And(0 <= x, x <= 1)`.

### Boolean operators

In function bodies, `and`/`or`/`not` are translated to Z3. In lambdas (contract expressions),
use `&`/`|`/`~` — see [Contracts](../concepts/contracts.md).

| Operator | Z3 encoding |
|---|---|
| `a and b` (body) | `z3.And(a, b)` |
| `a or b` (body) | `z3.Or(a, b)` |
| `not a` (body) | `z3.Not(a)` |
| `a & b` (contract lambda) | `z3.And(a, b)` |
| `a \| b` (contract lambda) | `z3.Or(a, b)` |
| `~a` (contract lambda) | `z3.Not(a)` |

### Builtins

| Builtin | Z3 encoding |
|---|---|
| `min(a, b)` | `z3.If(a <= b, a, b)` |
| `max(a, b)` | `z3.If(a >= b, a, b)` |
| `abs(x)` | `z3.If(x >= 0, x, -x)` |

`min` and `max` with more than two arguments are desugared recursively.

### Control flow

| Construct | Support |
|---|---|
| `if` / `elif` / `else` | Supported — translated to nested `z3.If` |
| Early `return` | Supported — translated via path accumulation |
| Ternary `a if cond else b` | Supported — direct `z3.If` |
| `pass` | Supported (no-op) |

### Variables and constants

| Construct | Support | Notes |
|---|---|---|
| Local variable assignment (`x = expr`) | Supported | Substituted symbolically |
| Module-level `int` / `float` constants | Supported | Injected as concrete Z3 values |
| Function parameters | Supported | Become Z3 symbolic variables |

### Calls to verified functions

Calls to functions listed in `contracts=` are supported. See
[Compositionality](../concepts/compositionality.md).

---

## Unsupported constructs

| Construct | Why not |
|---|---|
| `while` loops | Termination is undecidable. Proving loop correctness requires a loop invariant and ranking function — neither can be inferred automatically. |
| `for` loops (unbounded) | Same reason as `while`. Bounded `for i in range(N)` with literal `N` is unrolled up to 256 iterations. |
| Recursion | Requires a ranking function to prove termination, and inductive invariants for correctness. These are beyond SMT decidability. |
| `str`, `list`, `dict`, `set` | Outside the SMT integer/real arithmetic fragment. |
| `lambda` inside function body | AST structure prevents reliable source extraction. |
| Class methods with `self` | `self` introduces heap aliasing, outside the supported fragment. |
| `try` / `except` | Exceptional control flow is not modeled. |
| Generators, `yield` | Not modeled. |
| `import` statements in body | Side effects outside the model. |
| Calls to unverified functions | Raises `TranslationError`. Add the callee to `contracts=` with its own proof. |
| `x ** y` with symbolic `y` | Z3 cannot represent $x^y$ for symbolic $y$ in linear arithmetic. |
| Slicing (`a[i:j]`) | Sequences not supported. |
| Bitwise operators (`&`, `\|`, `^`, `~`, `<<`, `>>`) | Not in the integer/real arithmetic fragment. |

---

## Tips for Z3-friendly code

**1. Avoid nonlinear arithmetic when possible.**

$x \cdot y$ where both `x` and `y` are symbolic forces Z3 into nonlinear arithmetic,
which is undecidable in general. Z3 uses heuristics and may return `unknown`. If you can
express the property without multiplying two symbolic variables, do so.

**2. Keep functions short.**

The translator processes the entire function body in one Z3 context. Large functions with
many branches produce large formulas. Split complex logic into smaller `@verified` helpers
and use `contracts=` to compose them.

**3. Use `pre=` to bound the input domain.**

Tighter preconditions make the solver's job easier:

```python
# Harder for Z3:
@verified(post=lambda x, result: result >= 0)
def f(x: int) -> int: ...

# Easier: x is bounded
@verified(
    pre=lambda x: (0 <= x) & (x <= 1000),
    post=lambda x, result: result >= 0,
)
def f(x: int) -> int: ...
```

**4. Use `Annotated` markers for parameter bounds.**

Equivalent to `pre=`, but attached to the type — cleaner syntax and better IDE support:

```python
from provably.types import Between

@verified(post=lambda x, result: result >= 0)
def f(x: Annotated[int, Between(0, 1000)]) -> int: ...
```

**5. Guard division with `NotEq(0)`.**

```python
from provably.types import NotEq

# TranslationError without the guard (or a pre= lambda):
def safe_div(a: float, b: Annotated[float, NotEq(0)]) -> float:
    return a / b
```

**6. If Z3 times out (`cert.status == Status.UNKNOWN`):**

```python
from provably import configure
configure(timeout_ms=30_000)   # default: 5000ms
```

Then `clear_cache()` and re-import. If timeout persists: eliminate nonlinear terms,
break the function into smaller helpers, or use `@runtime_checked` as a fallback.
