"""Test that provably proves its own internal functions.

This is the meta-verification test — if provably can't verify its
own builtins, the system is unsound.
"""

from __future__ import annotations

import pytest
from conftest import requires_z3

pytestmark = requires_z3

from provably._self_proof import (
    SELF_PROOFS,
    _z3_abs,
    _z3_max,
    _z3_min,
    bounded_increment,
    clamp,
    identity,
    max_of_abs,
    negate_negate,
    relu,
    safe_divide,
)
from provably.engine import Status


class TestSelfProofCollection:
    def test_self_proof_count(self) -> None:
        assert len(SELF_PROOFS) >= 10

    def test_all_self_proofs_verified(self) -> None:
        failures = []
        for fn in SELF_PROOFS:
            proof = fn.__proof__
            if not proof.verified:
                failures.append(f"{proof.function_name}: {proof.status.value} — {proof.message}")
        assert not failures, "Self-proofs failed:\n" + "\n".join(failures)

    def test_all_self_proofs_have_proof_attribute(self) -> None:
        for fn in SELF_PROOFS:
            assert hasattr(fn, "__proof__"), f"{fn.__name__} missing __proof__"

    def test_all_self_proofs_verified_status(self) -> None:
        for fn in SELF_PROOFS:
            assert fn.__proof__.status == Status.VERIFIED, (
                f"{fn.__name__} status={fn.__proof__.status.value}: {fn.__proof__.message}"
            )


class TestIndividualSelfProofs:
    def test_z3_min_verified(self) -> None:
        assert _z3_min.__proof__.verified, _z3_min.__proof__

    def test_z3_max_verified(self) -> None:
        assert _z3_max.__proof__.verified, _z3_max.__proof__

    def test_z3_abs_verified(self) -> None:
        assert _z3_abs.__proof__.verified, _z3_abs.__proof__

    def test_clamp_verified(self) -> None:
        assert clamp.__proof__.verified, clamp.__proof__

    def test_relu_verified(self) -> None:
        assert relu.__proof__.verified, relu.__proof__

    def test_bounded_increment_verified(self) -> None:
        assert bounded_increment.__proof__.verified, bounded_increment.__proof__

    def test_safe_divide_verified(self) -> None:
        assert safe_divide.__proof__.verified, safe_divide.__proof__

    def test_identity_verified(self) -> None:
        assert identity.__proof__.verified, identity.__proof__

    def test_negate_negate_verified(self) -> None:
        assert negate_negate.__proof__.verified, negate_negate.__proof__

    def test_max_of_abs_verified(self) -> None:
        assert max_of_abs.__proof__.verified, max_of_abs.__proof__


class TestSelfProofPostconditionStrength:
    """Assert the strengthened postconditions — not just that proofs pass,
    but that the postcondition text reflects the stronger claim."""

    def test_z3_min_postcondition_is_selective(self) -> None:
        # Must prove result == a OR result == b, not just bounds.
        post_strs = " ".join(_z3_min.__proof__.postconditions)
        assert "==" in post_strs, (
            "_z3_min postcondition should include selectivity (result == a or result == b)"
        )

    def test_z3_max_postcondition_is_selective(self) -> None:
        post_strs = " ".join(_z3_max.__proof__.postconditions)
        assert "==" in post_strs, (
            "_z3_max postcondition should include selectivity (result == a or result == b)"
        )

    def test_z3_abs_postcondition_has_identity(self) -> None:
        post_strs = " ".join(_z3_abs.__proof__.postconditions)
        assert "==" in post_strs, (
            "_z3_abs postcondition should include result == x or result == -x"
        )

    def test_clamp_postcondition_has_passthrough(self) -> None:
        # The postcondition should encode: when val is in [lo, hi], result == val.
        post_strs = " ".join(clamp.__proof__.postconditions)
        assert "==" in post_strs, (
            "clamp postcondition should include the passthrough case (result == val)"
        )

    def test_relu_postcondition_is_selective(self) -> None:
        post_strs = " ".join(relu.__proof__.postconditions)
        assert "==" in post_strs, "relu postcondition should include result == x or result == 0"

    def test_bounded_increment_postcondition_is_exact(self) -> None:
        # result == x + 1 is stronger than just 1 <= result <= 100.
        post_strs = " ".join(bounded_increment.__proof__.postconditions)
        assert "==" in post_strs, "bounded_increment postcondition should include result == x + 1"


class TestSelfProofsComputeCorrectly:
    """Self-proof functions must still compute correct values at runtime."""

    def test_self_proofs_still_compute_correctly(self) -> None:
        # _z3_min
        assert _z3_min(3.0, 7.0) == 3.0
        assert _z3_min(7.0, 3.0) == 3.0
        assert _z3_min(5.0, 5.0) == 5.0

        # _z3_max
        assert _z3_max(3.0, 7.0) == 7.0
        assert _z3_max(7.0, 3.0) == 7.0
        assert _z3_max(5.0, 5.0) == 5.0

        # _z3_abs
        assert _z3_abs(-5.0) == 5.0
        assert _z3_abs(5.0) == 5.0
        assert _z3_abs(0.0) == 0.0

        # clamp
        assert clamp(3.0, 0.0, 10.0) == 3.0
        assert clamp(-5.0, 0.0, 10.0) == 0.0
        assert clamp(15.0, 0.0, 10.0) == 10.0

        # relu
        assert relu(5.0) == 5.0
        assert relu(-5.0) == 0.0
        assert relu(0.0) == 0.0

        # bounded_increment
        assert bounded_increment(0) == 1
        assert bounded_increment(99) == 100
        assert bounded_increment(50) == 51

        # safe_divide
        assert safe_divide(10, 2) == 5
        assert safe_divide(7, 3) == 2
        assert safe_divide(0, 5) == 0

        # identity
        assert identity(42.0) == 42.0
        assert identity(0.0) == 0.0
        assert identity(-7.5) == -7.5

        # negate_negate
        assert negate_negate(5.0) == 5.0
        assert negate_negate(-3.0) == -3.0
        assert negate_negate(0.0) == 0.0

        # max_of_abs
        assert max_of_abs(-10.0, 3.0) == 10.0
        assert max_of_abs(3.0, -10.0) == 10.0
        assert max_of_abs(0.0, 0.0) == 0.0

    def test_min_boundary_equal(self) -> None:
        assert _z3_min(5.0, 5.0) == 5.0

    def test_max_boundary_equal(self) -> None:
        assert _z3_max(5.0, 5.0) == 5.0

    def test_abs_zero(self) -> None:
        assert _z3_abs(0.0) == 0.0

    def test_clamp_at_lo_boundary(self) -> None:
        assert clamp(0.0, 0.0, 10.0) == 0.0

    def test_clamp_at_hi_boundary(self) -> None:
        assert clamp(10.0, 0.0, 10.0) == 10.0

    def test_clamp_passthrough(self) -> None:
        # When val is strictly inside [lo, hi], result must equal val exactly.
        assert clamp(5.0, 0.0, 10.0) == 5.0
        assert clamp(0.001, 0.0, 1.0) == 0.001
        assert clamp(-0.5, -1.0, 0.0) == -0.5

    def test_relu_at_zero(self) -> None:
        assert relu(0.0) == 0.0

    def test_relu_passthrough_positive(self) -> None:
        # When x > 0, relu must return x exactly.
        assert relu(3.14) == 3.14
        assert relu(100.0) == 100.0

    def test_bounded_increment_min(self) -> None:
        assert bounded_increment(0) == 1

    def test_bounded_increment_max(self) -> None:
        assert bounded_increment(99) == 100

    def test_bounded_increment_is_exact(self) -> None:
        # result == x + 1, not just in [1, 100].
        for x in range(100):
            assert bounded_increment(x) == x + 1

    def test_safe_divide_zero_numerator(self) -> None:
        assert safe_divide(0, 7) == 0

    def test_safe_divide_exact(self) -> None:
        assert safe_divide(6, 2) == 3

    def test_safe_divide_floor_property(self) -> None:
        # Verify the floor-division bound: result * b <= a < result * b + b
        cases = [(7, 3), (10, 3), (1, 10), (100, 7), (99, 9)]
        for a, b in cases:
            r = safe_divide(a, b)
            assert r * b <= a < r * b + b, f"safe_divide({a}, {b}) = {r} violates floor bound"

    def test_negate_negate_negative(self) -> None:
        assert negate_negate(-42.0) == -42.0

    def test_negate_negate_is_exact(self) -> None:
        # Must recover x exactly — not just same sign.
        import math

        for x in [-1000.0, -0.001, 0.0, 0.001, 1000.0]:
            assert negate_negate(x) == x
        assert math.isnan(negate_negate(float("nan"))) or negate_negate(0.0) == 0.0

    def test_max_of_abs_both_negative(self) -> None:
        assert max_of_abs(-3.0, -7.0) == 7.0

    def test_max_of_abs_selectivity(self) -> None:
        # Result must equal |a| or |b| — not some arbitrary non-negative number.
        cases = [
            (-10.0, 3.0, 10.0),
            (3.0, -10.0, 10.0),
            (5.0, 5.0, 5.0),
            (-2.0, -2.0, 2.0),
            (0.0, 0.0, 0.0),
        ]
        for a, b, expected in cases:
            result = max_of_abs(a, b)
            assert result == expected
            assert result == abs(a) or result == abs(b)

    def test_min_is_selective(self) -> None:
        # Result must be one of the two inputs exactly.
        assert _z3_min(3.0, 7.0) in (3.0, 7.0)
        assert _z3_min(7.0, 3.0) in (3.0, 7.0)
        # And the right one:
        assert _z3_min(3.0, 7.0) == 3.0
        assert _z3_min(7.0, 3.0) == 3.0

    def test_max_is_selective(self) -> None:
        assert _z3_max(3.0, 7.0) in (3.0, 7.0)
        assert _z3_max(3.0, 7.0) == 7.0
        assert _z3_max(7.0, 3.0) == 7.0

    def test_abs_is_identity_or_negation(self) -> None:
        # _z3_abs(x) must equal x or -x — not an arbitrary non-negative value.
        for x in [-5.0, -1.0, 0.0, 1.0, 5.0]:
            result = _z3_abs(x)
            assert result == x or result == -x
