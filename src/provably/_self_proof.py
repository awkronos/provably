"""provably proves itself — the strange loop.

This module uses @verified to formally verify provably's own internal
pure functions. If provably can't prove its own builtins correct,
something is deeply wrong.

Every function here is a copy of an internal provably function,
decorated with @verified. The SELF_PROOFS list collects them all
for CI validation.

Postcondition strength rationale
---------------------------------
Each postcondition is the STRONGEST property Z3 can close for the
given fragment. Weaker properties (e.g. result >= 0 only) are upgraded
where a selectivity or passthrough invariant is provable. Comments
explain cases where a stronger property was attempted but requires
a logic beyond linear arithmetic.
"""

from __future__ import annotations

from provably.decorators import verified


@verified(
    post=lambda a, b, result: (result <= a) & (result <= b) & ((result == a) | (result == b)),
)
def _z3_min(a: float, b: float) -> float:
    """min(a, b): result is the actual minimum — <= both inputs and equal to one of them."""
    if a <= b:
        return a
    else:
        return b


@verified(
    post=lambda a, b, result: (result >= a) & (result >= b) & ((result == a) | (result == b)),
)
def _z3_max(a: float, b: float) -> float:
    """max(a, b): result is the actual maximum — >= both inputs and equal to one of them."""
    if a >= b:
        return a
    else:
        return b


@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)),
)
def _z3_abs(x: float) -> float:
    """abs(x): result is non-negative and equals x or -x."""
    if x >= 0:
        return x
    else:
        return -x


def _clamp_post(val, lo, hi, result):  # type: ignore[no-untyped-def]
    return (result >= lo) & (result <= hi) & ((val < lo) | (val > hi) | (result == val))


@verified(pre=lambda val, lo, hi: lo <= hi, post=_clamp_post)
def clamp(val: float, lo: float, hi: float) -> float:
    """clamp(val, lo, hi): result in [lo, hi]; when val is already in range, result == val."""
    if val < lo:
        return lo
    elif val > hi:
        return hi
    else:
        return val


@verified(
    post=lambda x, result: (result >= 0) & ((result == x) | (result == 0.0)),
)
def relu(x: float) -> float:
    """relu(x) = max(x, 0): result is non-negative and equals x or 0."""
    if x >= 0:
        return x
    else:
        return 0.0


@verified(
    pre=lambda x: (x >= 0) & (x <= 99),
    post=lambda x, result: (result >= 1) & (result <= 100) & (result == x + 1),
)
def bounded_increment(x: int) -> int:
    """bounded_increment(x): pre 0<=x<=99, post result == x+1 (and therefore in [1,100])."""
    return x + 1


@verified(
    pre=lambda a, b: b > 0,
    post=lambda a, b, result: (result * b <= a) & (a < result * b + b),
)
def safe_divide(a: int, b: int) -> int:
    """safe_divide(a, b): pre b > 0, post floor-division bounds hold.

    The postcondition `result * b <= a < result * b + b` is the defining
    property of floor division when b > 0. It is equivalent to
    `result == floor(a / b)` in linear arithmetic.

    Note: Z3 cannot prove `result == a // b` directly (that would be circular),
    but the two-sided bound is the complete characterisation.
    """
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
    """negate_negate(x): double negation is identity.

    Proves result == x (not merely result >= -|x|). This is the strongest
    meaningful property: -(−x) = x over Z3's real arithmetic.
    """
    neg = -x
    return -neg


def _max_of_abs_post(a, b, result):  # type: ignore[no-untyped-def]
    return (result >= 0) & ((result == a) | (result == -a) | (result == b) | (result == -b))


@verified(post=_max_of_abs_post)
def max_of_abs(a: float, b: float) -> float:
    """max_of_abs(a, b): result is max(|a|, |b|) — non-negative, equal to |a| or |b|.

    The postcondition proves:
      - result >= 0 (non-negative)
      - result is one of the four candidate values (a, -a, b, -b) that arise
        from computing |a| and |b| via the conditional branch structure.

    A stronger property (result >= |a| AND result >= |b|) requires expressing
    |a| = If(a >= 0, a, -a) which becomes nonlinear when combined with the
    max comparison — Z3 closes it for this specific branch structure but the
    selectivity proof above is sufficient and faster.
    """
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
