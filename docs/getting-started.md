# Getting Started

## Install

### pip

```bash
pip install provably[z3]
```

The `[z3]` extra installs `z3-solver` (the official Python bindings for Microsoft's Z3 SMT solver).
Without it, `@verified` raises `RuntimeError` at decoration time, but `@runtime_checked` works normally.

### uv

```bash
uv add "provably[z3]"
```

### Verify the install

```python
python -c "import provably; import z3; print('Z3', z3.get_version_string())"
```

## Your first proof

Write a function. Add a contract. Let provably check it.

```python
from provably import verified

@verified(
    pre=lambda x, y: (x >= 0) & (y >= 0),
    post=lambda x, y, result: result >= 0,
)
def add(x: int, y: int) -> int:
    return x + y
```

When Python loads this module, provably:

1. Retrieves the source of `add` via `inspect.getsource`.
2. Parses it with Python's `ast` module.
3. Translates the AST into Z3 expressions.
4. Asserts the **negation** of the postcondition under the precondition.
5. Asks Z3: "Is there any input where the pre holds but the post fails?"
6. Z3 answers `unsat` — no such input exists.

The result is stored in `add.__proof__`:

```python
proof = add.__proof__
print(proof.verified)        # True
print(proof.solver_time_ms)  # e.g. 1.1
print(proof.status)          # Status.VERIFIED
```

## What Q.E.D. means

*Quod erat demonstrandum* — "what was to be demonstrated."

In provably, `__proof__.verified == True` is not a test result. It means the Z3 SMT solver
has determined that the verification condition (VC) is **unsatisfiable** — there exists no
assignment of values to the input variables that satisfies the precondition and violates the
postcondition simultaneously. This is a mathematical proof, not a probabilistic assertion.

Concretely, for a function $f$ with precondition $P$ and postcondition $Q$:

$$\text{VC} \;=\; P(\bar{x}) \;\Rightarrow\; Q(\bar{x},\, f(\bar{x}))$$

provably checks that $\neg\,\text{VC}$ is unsatisfiable. The SMT query is:

$$\text{check}\bigl(P(\bar{x}) \;\land\; \neg\, Q(\bar{x}, \mathit{ret})\bigr)$$

If `unsat`: the implication holds universally. If `sat`: Z3 returns a model — a concrete
counterexample.

## What to do next

- **Learn the contract syntax** — [Contracts](concepts/contracts.md)
- **Embed constraints in types** — [Refinement types](concepts/refinement-types.md)
- **Understand the limits** — [Soundness](concepts/soundness.md)
- **Add proofs to CI** — [Pytest integration](guides/pytest.md)
