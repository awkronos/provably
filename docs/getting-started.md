# Getting Started

## Install

=== "pip"

    ```bash
    pip install provably
    ```

=== "uv"

    ```bash
    uv add provably
    ```

```python
python -c "import provably; import z3; print('Z3', z3.get_version_string())"
# Z3 4.13.0
```

---

## Your first proof

```python
from provably import verified

@verified(
    pre=lambda x, y: (x >= 0) & (y >= 0),
    post=lambda x, y, result: result >= 0,
)
def add(x: int, y: int) -> int:
    return x + y

proof = add.__proof__
proof.verified        # True
proof.solver_time_ms  # 1.1
proof.status          # Status.VERIFIED
str(proof)            # "[Q.E.D.] add"
```

At import time, provably:

1. Parses the function body into a Python AST.
2. Translates the AST into Z3 expressions.
3. Asserts the **negation** of the postcondition under the precondition.
4. Z3 answers `unsat` -- no input violates the contract.

---

## A stronger example

```python
from provably import verified

@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result * b <= a) & (a < result * b + b),
)
def floor_div(a: int, b: int) -> int:
    return a // b

floor_div.__proof__.verified        # True
floor_div.__proof__.solver_time_ms  # ~2ms
str(floor_div.__proof__)            # "[Q.E.D.] floor_div"
```

The postcondition `result * b <= a < result * b + b` is the complete characterisation
of floor division when `b > 0`. Z3 proves it for **all** integers `a` and all positive `b`.

---

## Counterexamples

When a contract is wrong, Z3 produces the exact input that breaks it:

```python
from provably import verified

@verified(
    pre=lambda n: n >= 0,
    post=lambda n, result: result * result == n,   # wrong: isqrt != exact sqrt
)
def bad_isqrt(n: int) -> int:
    r = 0
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r

cert = bad_isqrt.__proof__
cert.verified        # False
cert.status          # Status.COUNTEREXAMPLE
cert.counterexample  # {'n': 2, '__return__': 1}
# isqrt(2) = 1, but 1*1 != 2. The contract is wrong, not the function.
```

Fix the postcondition to match what the function actually guarantees:

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

isqrt.__proof__.verified  # True
str(isqrt.__proof__)      # "[Q.E.D.] isqrt"
```

---

## What Q.E.D. means

`__proof__.verified == True` means the Z3 SMT solver determined that the verification
condition (VC) is **unsatisfiable** -- no assignment of input values satisfies the
precondition while violating the postcondition. This is a mathematical proof.

For function $f$ with precondition $P$ and postcondition $Q$:

$$\text{VC} \;=\; P(\bar{x}) \;\Rightarrow\; Q(\bar{x},\, f(\bar{x}))$$

provably checks that $\neg\,\text{VC}$ is unsatisfiable:

$$\text{check}\bigl(P(\bar{x}) \;\land\; \neg\, Q(\bar{x}, \mathit{ret})\bigr)$$

If `unsat`: the implication holds universally. If `sat`: Z3 returns a concrete counterexample.

!!! theorem "What the proof covers"
    `VERIFIED` covers **all possible inputs** satisfying the precondition. For integer
    arithmetic, this is exact. For `float`, Z3 reasons over mathematical reals, not
    IEEE 754 -- see [Soundness](concepts/soundness.md).

---

## Next

- [Contracts](concepts/contracts.md) -- pre/post lambda syntax
- [Refinement types](concepts/refinement-types.md) -- constraints in type annotations
- [Soundness](concepts/soundness.md) -- what the proof does and does not cover
- [Pytest integration](guides/pytest.md) -- proofs in CI
