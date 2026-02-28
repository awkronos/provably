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

    def test_relu_at_zero(self) -> None:
        assert relu(0.0) == 0.0

    def test_bounded_increment_min(self) -> None:
        assert bounded_increment(0) == 1

    def test_bounded_increment_max(self) -> None:
        assert bounded_increment(99) == 100

    def test_safe_divide_zero_numerator(self) -> None:
        assert safe_divide(0, 7) == 0

    def test_safe_divide_exact(self) -> None:
        assert safe_divide(6, 2) == 3

    def test_negate_negate_negative(self) -> None:
        assert negate_negate(-42.0) == -42.0

    def test_max_of_abs_both_negative(self) -> None:
        assert max_of_abs(-3.0, -7.0) == 7.0
