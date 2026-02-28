# Getting Started

## Install

=== "pip"

    ```bash
    pip install provably[z3]
    ```

=== "uv"

    ```bash
    uv add "provably[z3]"
    ```

The `[z3]` extra installs `z3-solver` (Microsoft's Z3 SMT solver Python bindings).
Without it, `@verified` raises `RuntimeError` at decoration time, but `@runtime_checked` works normally.

Verify the install:

```python
python -c "import provably; import z3; print('Z3', z3.get_version_string())"
# Z3 4.13.0
```

---

## Your first proof

Write a function. State its contract. Let provably check it.

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
print(proof.solver_time_ms)  # 1.1
print(proof.status)          # Status.VERIFIED
print(proof)                 # [Q.E.D.] add
```

---

## A stronger example: floor-division bounds

```python
from provably import verified

@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result * b <= a) & (a < result * b + b),
)
def floor_div(a: int, b: int) -> int:
    return a // b

cert = floor_div.__proof__
print(cert.verified)        # True
print(cert.solver_time_ms)  # ~2ms
```

The postcondition `result * b <= a < result * b + b` is the complete mathematical
characterisation of floor division when `b > 0`. Z3 proves it holds for all integers `a`
and all positive `b` — not just the cases you thought to test.

---

## When proof fails: counterexamples

```python
from provably import verified

@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result * result == n,   # wrong: isqrt ≠ exact square root
)
def bad_isqrt(n: int) -> int:
    r = 0
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r

cert = bad_isqrt.__proof__
print(cert.verified)        # False
print(cert.status)          # Status.COUNTEREXAMPLE
print(cert.counterexample)  # {'n': 2, '__return__': 1}
# isqrt(2) = 1, but 1 * 1 = 1 ≠ 2. The contract is wrong, not the function.
```

Z3 doesn't just tell you the proof failed — it gives you the exact input that breaks the
contract. Run `bad_isqrt(2)` yourself and you'll see the discrepancy. Fix the postcondition:

```python
@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: (result * result <= n) & (n < (result + 1) * (result + 1)),
)
def isqrt(n: int) -> int:
    r = 0
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r

print(isqrt.__proof__.verified)  # True  [Q.E.D.]
```

---

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

!!! theorem "What the proof covers"
    A `VERIFIED` proof covers **all possible inputs** satisfying the precondition — not
    the inputs you thought to test, not a random sample, not an approximation. For integer
    arithmetic, this is exact. For float arithmetic, note that Z3 reasons over mathematical
    reals, not IEEE 754 — see [Soundness](concepts/soundness.md) for the caveat.

---

## What to do next

- **Learn the contract syntax** — [Contracts](concepts/contracts.md)
- **Embed constraints in types** — [Refinement types](concepts/refinement-types.md)
- **Understand the limits** — [Soundness](concepts/soundness.md)
- **Add proofs to CI** — [Pytest integration](guides/pytest.md)
