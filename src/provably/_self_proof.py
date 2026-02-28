"""provably proves itself — the strange loop.

This module uses @verified to formally verify provably's own internal
pure functions. If provably can't prove its own builtins correct,
something is deeply wrong.

Every function here is a copy of an internal provably function,
decorated with @verified. The SELF_PROOFS list collects them all
for CI validation.
"""

from __future__ import annotations

from provably.decorators import verified


@verified(
    post=lambda a, b, result: (result <= a) & (result <= b),
)
def _z3_min(a: float, b: float) -> float:
    """min(a, b): result is <= both a and b."""
    if a <= b:
        return a
    else:
        return b


@verified(
    post=lambda a, b, result: (result >= a) & (result >= b),
)
def _z3_max(a: float, b: float) -> float:
    """max(a, b): result is >= both a and b."""
    if a >= b:
        return a
    else:
        return b


@verified(
    post=lambda x, result: result >= 0,
)
def _z3_abs(x: float) -> float:
    """abs(x): result is non-negative."""
    if x >= 0:
        return x
    else:
        return -x


@verified(
    pre=lambda val, lo, hi: lo <= hi,
    post=lambda val, lo, hi, result: (result >= lo) & (result <= hi),
)
def clamp(val: float, lo: float, hi: float) -> float:
    """clamp(val, lo, hi): result is in [lo, hi] when lo <= hi."""
    if val < lo:
        return lo
    elif val > hi:
        return hi
    else:
        return val


@verified(
    post=lambda x, result: result >= 0,
)
def relu(x: float) -> float:
    """relu(x) = max(x, 0): result is non-negative."""
    if x >= 0:
        return x
    else:
        return 0.0


@verified(
    pre=lambda x: (x >= 0) & (x <= 99),
    post=lambda x, result: (result >= 1) & (result <= 100),
)
def bounded_increment(x: int) -> int:
    """bounded_increment(x): pre 0<=x<=99, post 1<=result<=100."""
    return x + 1


@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result * b <= a) & (a < result * b + b),
)
def safe_divide(a: int, b: int) -> int:
    """safe_divide(a, b): pre b > 0, post floor-division bounds hold."""
    return a // b


@verified(
    post=lambda x, result: result == x,
)
def identity(x: float) -> float:
    """identity(x): result equals x."""
    return x


@verified(
    post=lambda x, result: result == x,
)
def negate_negate(x: float) -> float:
    """negate_negate(x): double negation is identity."""
    neg = -x
    return -neg


@verified(
    post=lambda a, b, result: result >= 0,
)
def max_of_abs(a: float, b: float) -> float:
    """max_of_abs(a, b): max(|a|, |b|) is non-negative."""
    abs_a = a if a >= 0 else -a
    abs_b = b if b >= 0 else -b
    if abs_a >= abs_b:
        return abs_a
    else:
        return abs_b


# Collect all self-proof functions for CI validation.
SELF_PROOFS = [
    _z3_min,
    _z3_max,
    _z3_abs,
    clamp,
    relu,
    bounded_increment,
    safe_divide,
    identity,
    negate_negate,
    max_of_abs,
]
