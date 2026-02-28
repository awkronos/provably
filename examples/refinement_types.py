"""Using refinement types with typing.Annotated.

Refinement types let you embed proof obligations directly in function signatures.
No separate pre= / post= lambdas needed — the types carry the contract.

Demonstrates:
  - Ge, Le, Gt, Lt, Between, NotEq markers
  - How @verified reads annotations automatically
  - Mixing refinement types with explicit contracts
  - Convenience aliases: Positive, NonNegative, UnitInterval (if available)
"""

from __future__ import annotations

from typing import Annotated

from provably import verified
from provably.types import Ge, Le, Gt, Lt, Between, NotEq


# ---------------------------------------------------------------------------
# 1. Basic bounds — Ge, Le
# ---------------------------------------------------------------------------

print("=== 1. Basic bounds (Ge, Le) ===")


@verified
def nonneg_double(x: Annotated[float, Ge(0)]) -> Annotated[float, Ge(0)]:
    """x >= 0  =>  x * 2 >= 0."""
    return x * 2


print(f"nonneg_double: {nonneg_double.__proof__}")
print(f"  nonneg_double(5) = {nonneg_double(5)}")
print()


@verified
def bounded_scale(x: Annotated[float, Ge(0), Le(1)]) -> Annotated[float, Ge(0), Le(100)]:
    """x in [0, 1]  =>  x * 100 in [0, 100]."""
    return x * 100


print(f"bounded_scale: {bounded_scale.__proof__}")
print(f"  bounded_scale(0.5) = {bounded_scale(0.5)}")
print()


# ---------------------------------------------------------------------------
# 2. Strict bounds — Gt, Lt
# ---------------------------------------------------------------------------

print("=== 2. Strict bounds (Gt, Lt) ===")


@verified
def positive_ratio(
    a: Annotated[float, Gt(0)],
    b: Annotated[float, Gt(0)],
) -> Annotated[float, Gt(0)]:
    """a, b > 0  =>  a + b > 0."""
    return a + b


print(f"positive_ratio: {positive_ratio.__proof__}")
print(f"  positive_ratio(3, 4) = {positive_ratio(3, 4)}")
print()


# ---------------------------------------------------------------------------
# 3. Range constraints — Between
# ---------------------------------------------------------------------------

print("=== 3. Range constraints (Between) ===")


@verified
def to_unit(
    x: Annotated[float, Between(0, 10)],
) -> Annotated[float, Between(0, 1)]:
    """x in [0, 10]  =>  x / 10 in [0, 1]."""
    return x / 10


print(f"to_unit: {to_unit.__proof__}")
print(f"  to_unit(7.5) = {to_unit(7.5)}")
print()


@verified
def lerp_unit(
    a: Annotated[float, Between(0, 1)],
    b: Annotated[float, Between(0, 1)],
    t: Annotated[float, Between(0, 1)],
) -> Annotated[float, Between(0, 1)]:
    """Linear interpolation between two unit values stays in [0, 1]."""
    return a + (b - a) * t


print(f"lerp_unit: {lerp_unit.__proof__}")
print(f"  lerp_unit(0.2, 0.8, 0.5) = {lerp_unit(0.2, 0.8, 0.5)}")
print()


# ---------------------------------------------------------------------------
# 4. NotEq — exclude a specific value
# ---------------------------------------------------------------------------

print("=== 4. Non-zero divisor (NotEq) ===")


@verified(
    post=lambda x, divisor, result: (result >= 0),
)
def safe_normalize(
    x: Annotated[float, Ge(0)],
    divisor: Annotated[float, Gt(0)],
) -> float:
    """Divide x by a guaranteed positive divisor."""
    return x / divisor


print(f"safe_normalize: {safe_normalize.__proof__}")
print(f"  safe_normalize(10.0, 4.0) = {safe_normalize(10.0, 4.0)}")
print()


# ---------------------------------------------------------------------------
# 5. Mixing refinement types and explicit contracts
# ---------------------------------------------------------------------------

print("=== 5. Mixed refinement + explicit contract ===")


@verified(
    pre=lambda val, lo, hi: lo <= hi,
    post=lambda val, lo, hi, result: (result >= lo) & (result <= hi),
)
def clamp(val: float, lo: float, hi: float) -> float:
    """Clamp with explicit pre/post (not refinement types)."""
    if val < lo:
        return lo
    elif val > hi:
        return hi
    return val


print(f"clamp: {clamp.__proof__}")
print(f"  clamp(15, 0, 10) = {clamp(15, 0, 10)}")
print(f"  clamp(-3, 0, 10) = {clamp(-3, 0, 10)}")
print()


# ---------------------------------------------------------------------------
# 6. What failure looks like — annotation says Ge(0) but function can go negative
# ---------------------------------------------------------------------------

print("=== 6. Annotation violation detected ===")


@verified
def wrong_abs(x: float) -> Annotated[float, Ge(0)]:
    """Claims to return >= 0 but returns x directly (can be negative)."""
    return x  # BUG: should be abs(x)


cert = wrong_abs.__proof__
print(f"wrong_abs: {cert}")
print(f"  Status: {cert.status.value}")
if cert.counterexample:
    print(f"  Counterexample: {cert.counterexample}")
print()


# ---------------------------------------------------------------------------
# 7. Convenience aliases (documented intent — xfail gracefully if not present)
# ---------------------------------------------------------------------------

print("=== 7. Convenience aliases ===")

try:
    from provably.types import Positive, NonNegative, UnitInterval  # type: ignore[attr-defined]

    @verified
    def scale_positive(x: Annotated[float, Positive]) -> Annotated[float, Positive]:
        return x * 2

    @verified
    def clip_unit(x: Annotated[float, UnitInterval]) -> Annotated[float, UnitInterval]:
        return x * 0.5

    print(f"scale_positive (Positive): {scale_positive.__proof__}")
    print(f"clip_unit (UnitInterval):  {clip_unit.__proof__}")

except ImportError:
    print("Positive / NonNegative / UnitInterval aliases not yet in provably.types")
    print("Define them as: Positive = Gt(0), NonNegative = Ge(0), UnitInterval = Between(0, 1)")
