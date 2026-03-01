# Supported Python Subset

## Supported

### Types

| Python type | Z3 sort | Notes |
|---|---|---|
| `int` | `IntSort` | Mathematical integers (unbounded) |
| `float` | `RealSort` | Mathematical reals, not IEEE 754 |
| `bool` | `BoolSort` | |
| `Annotated[T, *markers]` | Same as `T` | Markers become preconditions |

### Arithmetic

| Operator | Z3 encoding | Notes |
|---|---|---|
| `+`, `-` | direct | |
| `*` | `x * y` | Nonlinear if both symbolic -- may be slow |
| `/` | real division | `y != 0` must be in `pre` or refinement |
| `//` | Z3 int division | Floor division on `IntSort` |
| `%` | `x - y * (x // y)` | |
| `**n` | unrolled multiply | `n` must be literal 0--3 |
| `-x`, `+x` | direct | |
| `math.pi`, `math.e` | Z3 real constants | Attribute access on `math` module |

### Comparisons

All six: `<`, `<=`, `>`, `>=`, `==`, `!=`. Chained comparisons (`0 <= x <= 1`)
desugared to `z3.And(...)`.

### Boolean operators

| Context | Syntax | Z3 encoding |
|---|---|---|
| Function body | `and`/`or`/`not` | `z3.And`/`z3.Or`/`z3.Not` |
| Contract lambda | `&`/`\|`/`~` | `z3.And`/`z3.Or`/`z3.Not` |

### Builtins

| Builtin | Z3 encoding | Notes |
|---|---|---|
| `min(a, b)` | `z3.If(a <= b, a, b)` | 2 args only |
| `max(a, b)` | `z3.If(a >= b, a, b)` | 2 args only |
| `abs(x)` | `z3.If(x >= 0, x, -x)` | |
| `pow(x, n)` | unrolled multiplication | Same as `**`; literal `n` in 0--3 |
| `bool(x)` | `z3.If(x != 0, 1, 0)` | Nonzero test; identity for `bool` |
| `int(x)` | `z3.ToInt(x)` | Identity for `int`; `ToInt` for real; `If` for bool |
| `float(x)` | `z3.ToReal(x)` | Identity for `float`; `ToReal` for int; `If` for bool |
| `len(x)` | uninterpreted `>= 0` | Axiom: `len(x) >= 0` |
| `round(x)` | `z3.ToInt(x)` | Identity for `int` |
| `sum(...)` | folded `+` | |
| `any(...)` | folded `z3.Or` | |
| `all(...)` | folded `z3.And` | |

### Control flow

| Construct | Translation | Notes |
|---|---|---|
| `if`/`elif`/`else` | Nested `z3.If` | |
| Early `return` | Path accumulation | |
| Ternary `a if cond else b` | `z3.If` | |
| `while cond: ...` | Bounded unrolling | Max 256 iterations |
| `match`/`case` | Nested `z3.If` | Python 3.10+. Literal, singleton, wildcard, guards. |
| `pass` | No-op | |

### Variables and assignments

| Construct | Notes |
|---|---|
| Local assignment (`x = expr`) | Symbolic substitution |
| Augmented assignment (`x += expr`, `-=`, `*=`, etc.) | Desugared to `x = x op expr` |
| Walrus operator (`(x := expr)`) | Inline assignment; binds in enclosing scope |
| Module-level `int`/`float` constants | Concrete Z3 values |
| Function parameters | Z3 symbolic variables |
| `assert expr` | Translated to Z3 proof obligation |

### Returns

| Construct | Notes |
|---|---|
| Single value `return x` | Standard |
| Tuple `return (a, b, ...)` | Z3 datatype with `__tuple_N_get_i` accessors |
| Tuple unpacking `x, y = func(...)` | Supported via accessor axioms |
| Constant subscript `t[0]`, `t[1]` | Integer literal indices on tuple-typed expressions |

### Verified function calls

Via `contracts=`. See [Compositionality](../concepts/compositionality.md).

---

## Unsupported

| Construct | Reason |
|---|---|
| Unbounded `while` / `for` | Bounded loops (max 256 iterations) are supported; unbounded raises `TranslationError` |
| Recursion | Requires ranking function + inductive invariants |
| `str`, `list`, `dict`, `set` | Outside SMT arithmetic fragment |
| `lambda` in body | AST prevents source extraction |
| `self` methods | Heap aliasing outside fragment |
| `try`/`except` | Not modeled |
| Generators, `yield` | Not modeled |
| `import` in body | Side effects outside model |
| Unverified calls | `TranslationError`. Add to `contracts=` or inline. |
| `x ** y` (symbolic `y`) | Not representable in linear arithmetic |
| Slicing, bitwise ops | Not in arithmetic fragment |
| Structural `match` patterns | Class, star, and mapping patterns raise `TranslationError` |

---

## Tips

**1. Avoid nonlinear arithmetic.** `x * y` with two symbolic variables forces Z3
into an undecidable fragment. Reformulate if possible.

**2. Keep functions short.** Split into `@verified` helpers, compose with `contracts=`.

**3. Bound inputs.** Tighter preconditions make the solver's job easier:

```python
@verified(
    pre=lambda x: (0 <= x) & (x <= 1000),
    post=lambda x, result: result >= 0,
)
def f(x: int) -> int: ...
```

**4. Use `Annotated` markers** instead of `pre=` for parameter bounds:

```python
@verified(post=lambda x, result: result >= 0)
def f(x: Annotated[int, Between(0, 1000)]) -> int: ...
```

**5. Guard division** with `NotEq(0)`:

```python
def safe_div(a: float, b: Annotated[float, NotEq(0)]) -> float:
    return a / b
```

**6. Timeout?** Increase it, eliminate nonlinear terms, split the function, or fall back
to `@runtime_checked`:

```python
from provably import configure
configure(timeout_ms=30_000)
```
