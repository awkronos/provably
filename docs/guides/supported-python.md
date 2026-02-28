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
| `x / y` | `x / y` (real) | `y != 0` must be in `pre` |
| `x // y` | `z3.ToInt(x / y)` | Integer floor division |
| `x % y` | `x - y * z3.ToInt(x / y)` | |
| `x ** n` | `x * x * ...` (n times) | `n` must be a concrete integer literal |
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

Chained comparisons (`0 <= x <= 1`) are supported and desugared to `0 <= x and x <= 1`.

### Boolean operators

| Operator | Z3 encoding |
|---|---|
| `a and b` | `z3.And(a, b)` |
| `a or b` | `z3.Or(a, b)` |
| `not a` | `z3.Not(a)` |

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
| `if` / `elif` / `else` | Supported — translated to `z3.If` |
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
[Compositionality](compositionality.md).

---

## Unsupported constructs

| Construct | Why not |
|---|---|
| `while` loops | Termination is undecidable. Proving loop correctness requires a loop invariant and ranking function — neither can be inferred automatically. Use mathematical equivalents (closed-form expressions) or move loop logic into a helper with its own proof. |
| `for` loops | Same reason as `while`. |
| Recursion | Requires a ranking function to prove termination, and inductive invariants for correctness. These are beyond SMT decidability. |
| `str`, `list`, `dict`, `set` | Outside the SMT integer/real arithmetic fragment. Z3 has array and string theories, but provably does not currently translate them. |
| `lambda` inside function body | AST structure prevents reliable source extraction. |
| `class` methods (instance vars) | `self` introduces heap aliasing, which is outside the supported fragment. |
| `try` / `except` | Exceptional control flow is not modeled. |
| Generators, `yield` | Not modeled. |
| `import` statements in body | Side effects outside the model. |
| Calls to unverified functions | Raises `TranslationError`. Add the callee to `contracts=` with its own proof. |
| `x ** y` with symbolic `y` | Z3 cannot represent $x^y$ for symbolic $y$ in linear arithmetic. Use a concrete literal. |
| Slicing (`a[i:j]`) | Sequences not supported. |
| Bitwise operators (`&`, `|`, `^`, `~`, `<<`, `>>`) | Not in the integer/real arithmetic fragment. |

---

## Tips for Z3-friendly code

**1. Avoid nonlinear arithmetic when possible.**

$x \cdot y$ where both are symbolic forces Z3 into nonlinear integer arithmetic, which
is undecidable in general. Z3 uses heuristics and may return `unknown`. If you can express
the property without multiplying two symbolic variables (e.g., one is always a constant),
do so.

**2. Keep functions short.**

The translator processes the entire function body in one Z3 context. Large functions with
many branches produce large formulas. Split complex logic into smaller verified helpers and
use `contracts=` to compose.

**3. Use `pre=` to bound the input domain.**

Tighter preconditions make the solver's job easier:

```python
# Harder for Z3:
@verified(post=lambda x, result: result >= 0)
def f(x: int) -> int: ...

# Easier: x is bounded
@verified(pre=lambda x: 0 <= x <= 1000, post=lambda x, result: result >= 0)
def f(x: int) -> int: ...
```

**4. Use `Annotated` markers for parameter bounds.**

Equivalent to `pre=`, but attached to the type — cleaner syntax and better IDE support.

**5. Avoid division without a `NotEq(0)` guard.**

```python
# Will raise TranslationError at proof time (or produce an unsound proof):
def f(x: float, y: float) -> float:
    return x / y

# Correct:
def f(x: float, y: Annotated[float, NotEq(0)]) -> float:
    return x / y
```

**6. If Z3 times out (`cert.status == Status.UNKNOWN`):**

- Increase the timeout: `configure(timeout_ms=30_000)`.
- Simplify the function: break it into smaller helpers.
- Check for nonlinear arithmetic and eliminate if possible.
- Consider using `@runtime_checked` for production and proving a weaker, provable property.
