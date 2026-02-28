# How It Works

provably's core pipeline is: **Python source → AST → Z3 constraints → SMT query → proof or counterexample**.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    @verified decorator                       │
│                                                             │
│  1. inspect.getsource(fn)   ─→  source text                 │
│  2. ast.parse(source)       ─→  Python AST                  │
│  3. Translator.visit(ast)   ─→  Z3 expressions   (TCB)      │
│  4. build_vc(pre, body, post)  ─→  Z3 formula               │
│  5. solver.check(¬VC)       ─→  sat / unsat / unknown       │
│  6. attach __proof__        ─→  ProofCertificate              │
└─────────────────────────────────────────────────────────────┘
```

## Step 1: Source retrieval

```python
import inspect, ast

source = inspect.getsource(fn)
tree   = ast.parse(textwrap.dedent(source))
```

provably uses `inspect.getsource` rather than bytecode inspection because Z3 needs symbolic
expressions — not runtime values. This means the function must be defined in a file that
Python can read (not in a REPL `<string>` buffer). Lambdas defined outside a module file
are also not retrievable; use named functions.

## Step 2: AST translation (the TCB)

The `Translator` class walks the AST and emits Z3 expressions. This is the **Trusted
Computing Base (TCB)**: if there is a bug in the translator, a proof could be unsound.
The TCB is deliberately small and tested extensively.

Each parameter is introduced as a Z3 symbolic variable:

```python
# Python:    def clamp(x: float, lo: float, hi: float) -> float
# Translator creates:
x  = z3.Real('x')
lo = z3.Real('lo')
hi = z3.Real('hi')
```

Refinement markers from `typing.Annotated` are extracted and added as background assumptions:

```python
# x: Annotated[float, Between(0.0, 1.0)]
# becomes:
assumptions = [x >= 0.0, x <= 1.0]
```

Arithmetic and comparison AST nodes translate directly:

| Python AST node | Z3 expression |
|---|---|
| `BinOp(Add)` | `left + right` |
| `BinOp(Sub)` | `left - right` |
| `BinOp(Mult)` | `left * right` |
| `BinOp(FloorDiv)` | `z3.ToInt(left / right)` (integer) |
| `BinOp(Div)` | `left / right` (real) |
| `BinOp(Pow)` | `left ** right` (concrete exponent only) |
| `Compare(Lt)` | `left < right` |
| `Compare(Eq)` | `left == right` |
| `BoolOp(And)` | `z3.And(...)` |
| `BoolOp(Or)` | `z3.Or(...)` |
| `UnaryOp(Not)` | `z3.Not(...)` |
| `IfExp` (ternary) | `z3.If(cond, a, b)` |

Control flow is translated via **path encoding**: each branch generates a separate Z3
conditional. For `if/elif/else` chains, each branch contributes a `z3.If` expression for
the final return value.

Early returns are handled by accumulating a path condition and constructing the
corresponding conditional Z3 expression once all paths are collected.

## Step 3: Verification condition (VC)

Given precondition $P$, the translated body $F$, and postcondition $Q$:

$$\text{VC} = P(\bar{x}) \Rightarrow Q(\bar{x},\, F(\bar{x}))$$

provably checks $\neg\,\text{VC}$:

$$\text{check}\bigl(\,P(\bar{x}) \;\land\; \neg\,Q(\bar{x},\, \mathit{ret})\,\bigr)$$

where $\mathit{ret}$ is unified with $F(\bar{x})$ via an equality constraint.

## Step 4: SMT query

```python
solver = z3.Solver()
solver.set("timeout", timeout_ms)
solver.add(pre_constraints)
solver.add(z3.Not(post_constraint))
result = solver.check()  # unsat | sat | unknown
```

| Result | Meaning |
|---|---|
| `unsat` | No counterexample exists. The contract is a theorem. `cert.status = VERIFIED`. |
| `sat` | Z3 found a counterexample. `cert.status = COUNTEREXAMPLE`, `cert.counterexample` is populated. |
| `unknown` | Solver timed out or gave up. `cert.status = UNKNOWN`. |

## Step 5: Proof certificates

The result is attached to the function as `fn.__proof__` (a frozen `ProofCertificate` instance):

```python
@dataclass(frozen=True)
class ProofCertificate:
    function_name:  str
    source_hash:    str             # SHA-256 prefix of function source
    status:         Status          # VERIFIED | COUNTEREXAMPLE | UNKNOWN | ...
    preconditions:  tuple[str, ...] # human-readable Z3 strings
    postconditions: tuple[str, ...]
    counterexample: dict | None     # populated on COUNTEREXAMPLE
    message:        str             # human-readable summary
    solver_time_ms: float           # wall-clock milliseconds
    z3_version:     str

    @property
    def verified(self) -> bool: ...  # True iff status == VERIFIED
```

Proof certificates are **cached** by content hash (source + contract bytecode).
Calling `clear_cache()` invalidates the cache.

## The Trusted Computing Base

The TCB consists of:

1. **The `Translator` class** — Python AST → Z3. Bugs here can produce unsound proofs.
2. **`extract_refinements`** — `Annotated` markers → Z3 constraints.
3. **`python_type_to_z3_sort`** — Python types → Z3 sorts.
4. **Z3 itself** — an external solver maintained by Microsoft Research. provably trusts Z3.

Everything outside the TCB — the `@verified` decorator plumbing, the `ProofCertificate`
dataclass, the caching layer, `verify_module`, `@runtime_checked` — does not affect
soundness. A bug outside the TCB can produce incorrect metadata (e.g., a wrong `solver_time`)
but cannot produce a spurious `verified=True`.

See [Soundness](soundness.md) for the epistemological boundaries.
