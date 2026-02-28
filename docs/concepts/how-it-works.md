# How It Works

**Python source &rarr; AST &rarr; Z3 constraints &rarr; SMT query &rarr; proof or counterexample.**

## Architecture

<div class="pipeline-diagram">

```
┌─────────────────────────────────────────────────────────────┐
│                    @verified decorator                       │
│                                                             │
│  1. inspect.getsource(fn)   ->  source text                 │
│  2. ast.parse(source)       ->  Python AST                  │
│  3. Translator.visit(ast)   ->  Z3 expressions   (TCB)      │
│  4. build_vc(pre, body, post)  ->  Z3 formula               │
│  5. solver.check(not VC)    ->  sat / unsat / unknown       │
│  6. attach __proof__        ->  ProofCertificate             │
└─────────────────────────────────────────────────────────────┘
```

</div>

## Source retrieval

```python
import inspect, ast, textwrap

source = inspect.getsource(fn)
tree   = ast.parse(textwrap.dedent(source))
```

The function must be defined in a readable `.py` file -- not a REPL buffer or `exec()` string.

## AST translation (the TCB)

The `Translator` class (~500 LOC) walks the AST and emits Z3 expressions. This is the
**Trusted Computing Base**: a bug here produces unsound proofs.

Each parameter becomes a Z3 symbolic variable:

```python
# def clamp(x: float, lo: float, hi: float) -> float
x  = z3.Real('x')
lo = z3.Real('lo')
hi = z3.Real('hi')
```

Refinement markers become background assumptions:

```python
# x: Annotated[float, Between(0.0, 1.0)]
assumptions = [x >= 0.0, x <= 1.0]  # added to solver
```

### Translation table

| Python AST | Z3 expression | Notes |
|---|---|---|
| `x + y` | `x + y` | |
| `x * y` | `x * y` | Nonlinear if both symbolic |
| `x // y` | `x / y` on `IntSort` | Z3 int division = floor division |
| `x / y` | `x / y` on `RealSort` | Real, not IEEE 754 |
| `x ** n` | unrolled multiplication | Concrete `n` in 0--3 only |
| `if/elif/else` | nested `z3.If` | Path encoding |
| `a if c else b` | `z3.If(c, a, b)` | |
| `and`/`or`/`not` (body) | `z3.And`/`z3.Or`/`z3.Not` | |
| `min(a, b)` | `z3.If(a <= b, a, b)` | |
| `max(a, b)` | `z3.If(a >= b, a, b)` | |
| `abs(x)` | `z3.If(x >= 0, x, -x)` | |

!!! note "FloorDiv"
    Z3's `/` on `IntSort` is floor division (truncating toward negative infinity for
    positive divisors), matching Python's `//`. This is not `z3.ToInt(real / real)`.

Bounded `for i in range(N)` loops (literal `N`, max 256) are fully unrolled.

## Verification condition

Given precondition $P$, translated body $F$, postcondition $Q$:

$$\text{VC} = P(\bar{x}) \Rightarrow Q(\bar{x},\, F(\bar{x}))$$

provably checks $\neg\,\text{VC}$:

$$\text{check}\bigl(\,P(\bar{x}) \;\land\; \neg\,Q(\bar{x},\, \mathit{ret})\,\bigr)$$

## SMT query

```python
solver = z3.Solver()
solver.set("timeout", timeout_ms)
solver.add(pre_constraints)
solver.add(z3.Not(post_constraint))
result = solver.check()  # unsat | sat | unknown
```

| Result | Meaning | Certificate status |
|---|---|---|
| `unsat` | No counterexample exists | `VERIFIED` |
| `sat` | Counterexample found | `COUNTEREXAMPLE` |
| `unknown` | Solver timed out | `UNKNOWN` |

## Proof certificates

```python
@dataclass(frozen=True)
class ProofCertificate:
    function_name:  str
    source_hash:    str             # SHA-256 prefix
    status:         Status          # VERIFIED | COUNTEREXAMPLE | UNKNOWN | ...
    preconditions:  tuple[str, ...]
    postconditions: tuple[str, ...]
    counterexample: dict | None     # populated on COUNTEREXAMPLE
    message:        str
    solver_time_ms: float
    z3_version:     str

    @property
    def verified(self) -> bool: ...  # True iff status == VERIFIED
```

Cached by content hash (source + contract bytecode). `clear_cache()` forces re-verification.

## The Trusted Computing Base

| Component | Role | Risk |
|---|---|---|
| `Translator` | AST &rarr; Z3 | Bugs produce unsound proofs |
| `extract_refinements` | `Annotated` &rarr; Z3 constraints | Small, tested |
| `python_type_to_z3_sort` | Types &rarr; Z3 sorts | Trivial |
| Z3 | SMT solver | External, trusted |

Everything outside the TCB (decorator plumbing, caching, `verify_module`) cannot
produce a spurious `verified=True`.

!!! theorem "Self-verification"
    The self-proof module runs the entire TCB on functions it will later verify.
    If a translator regression breaks `_z3_min` or `clamp`, CI fails before merge.
    See [Self-Proof](../self-proof.md).
