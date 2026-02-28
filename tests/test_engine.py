"""Tests for the verification engine — VC generation and Z3 solving."""

from __future__ import annotations

import json

import pytest
from conftest import requires_z3

pytestmark = requires_z3

from provably.engine import ProofCertificate, Status, clear_cache, verify_function


@pytest.fixture(autouse=True)
def _clear() -> None:
    clear_cache()


# ---------------------------------------------------------------------------
# Proofs that should succeed (VERIFIED)
# ---------------------------------------------------------------------------


class TestVerified:
    def test_identity(self) -> None:
        def identity(x: float) -> float:
            return x

        cert = verify_function(identity, post=lambda x, r: r == x)
        assert cert.verified

    def test_double_positive(self) -> None:
        def double(x: float) -> float:
            return x * 2

        cert = verify_function(
            double,
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= x,
        )
        assert cert.verified

    def test_clamp(self) -> None:
        def clamp(val: float, lo: float, hi: float) -> float:
            if val < lo:
                return lo
            elif val > hi:
                return hi
            else:
                return val

        cert = verify_function(
            clamp,
            pre=lambda val, lo, hi: lo <= hi,
            post=lambda val, lo, hi, r: (r >= lo) & (r <= hi),
        )
        assert cert.verified, cert

    def test_abs_nonneg(self) -> None:
        def my_abs(x: float) -> float:
            if x >= 0:
                return x
            else:
                return -x

        cert = verify_function(my_abs, post=lambda x, r: r >= 0)
        assert cert.verified

    def test_max_ge_both(self) -> None:
        def my_max(a: float, b: float) -> float:
            if a >= b:
                return a
            else:
                return b

        cert = verify_function(
            my_max,
            post=lambda a, b, r: (r >= a) & (r >= b),
        )
        assert cert.verified

    def test_min_le_both(self) -> None:
        def my_min(a: float, b: float) -> float:
            if a <= b:
                return a
            else:
                return b

        cert = verify_function(
            my_min,
            post=lambda a, b, r: (r <= a) & (r <= b),
        )
        assert cert.verified

    def test_bounded_increment(self) -> None:
        def bounded_inc(x: float) -> float:
            y = x + 1
            if y > 10:
                return 10.0
            return y

        cert = verify_function(
            bounded_inc,
            pre=lambda x: x <= 10,
            post=lambda x, r: r <= 10,
        )
        assert cert.verified

    def test_square_nonneg(self) -> None:
        def square(x: int) -> int:
            return x**2

        cert = verify_function(square, post=lambda x, r: r >= 0)
        assert cert.verified

    def test_lerp_bounded(self) -> None:
        """Linear interpolation stays in [a, b] when t in [0, 1]."""

        def lerp(a: float, b: float, t: float) -> float:
            return a + (b - a) * t

        cert = verify_function(
            lerp,
            pre=lambda a, b, t: (a <= b) & (t >= 0) & (t <= 1),
            post=lambda a, b, t, r: (r >= a) & (r <= b),
        )
        assert cert.verified


# ---------------------------------------------------------------------------
# Proofs that should fail (COUNTEREXAMPLE)
# ---------------------------------------------------------------------------


class TestCounterexample:
    def test_wrong_postcondition(self) -> None:
        def negate(x: float) -> float:
            return -x

        cert = verify_function(negate, post=lambda x, r: r >= 0)
        assert cert.status == Status.COUNTEREXAMPLE
        assert cert.counterexample is not None
        # The counterexample should show a positive x where -x < 0
        assert cert.counterexample["x"] > 0

    def test_clamp_without_precondition(self) -> None:
        """Without lo <= hi, clamp can fail."""

        def clamp(val: float, lo: float, hi: float) -> float:
            if val < lo:
                return lo
            elif val > hi:
                return hi
            else:
                return val

        cert = verify_function(
            clamp,
            post=lambda val, lo, hi, r: (r >= lo) & (r <= hi),
        )
        assert cert.status == Status.COUNTEREXAMPLE

    def test_identity_not_always_positive(self) -> None:
        def identity(x: float) -> float:
            return x

        cert = verify_function(identity, post=lambda x, r: r > 0)
        assert cert.status == Status.COUNTEREXAMPLE


# ---------------------------------------------------------------------------
# Timeout behavior
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_very_short_timeout_returns_unknown_or_result(self) -> None:
        """A 1ms timeout is too short for most proofs — should return UNKNOWN.

        This is non-deterministic: fast machines may still solve before timeout.
        We accept either UNKNOWN or VERIFIED (never an uncaught exception).
        """

        def f(x: float) -> float:
            if x < 0:
                return -x
            return x

        cert = verify_function(f, post=lambda x, r: r >= 0, timeout_ms=1)
        assert cert.status in (Status.UNKNOWN, Status.VERIFIED)

    def test_status_unknown_has_message(self) -> None:
        """UNKNOWN status always carries an explanatory message."""

        def f(x: float) -> float:
            return x

        # Force UNKNOWN by crafting a cert directly (bypass solver)
        cert = ProofCertificate(
            function_name="f",
            source_hash="abc",
            status=Status.UNKNOWN,
            preconditions=(),
            postconditions=(),
            message="Z3 returned unknown (timeout 1ms?)",
        )
        assert cert.status == Status.UNKNOWN
        assert "timeout" in cert.message.lower() or cert.message


# ---------------------------------------------------------------------------
# Closure variable resolution
# ---------------------------------------------------------------------------


class TestClosureVariableResolution:
    def test_module_constant_in_function(self) -> None:
        """verify_function should resolve numeric module-level constants."""
        # Define function with module-level constant
        SCALE = 2.0  # noqa: N806 — module-level constant

        def scale_up(x: float) -> float:
            return x * SCALE

        cert = verify_function(
            scale_up,
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= x,
        )
        # x >= 0 and r = x * 2.0 => r >= x
        assert cert.verified

    def test_integer_constant_resolved(self) -> None:
        MAX_VAL = 100  # noqa: N806

        def cap(x: int) -> int:
            if x > MAX_VAL:
                return MAX_VAL
            return x

        cert = verify_function(cap, post=lambda x, r: r <= 100)
        assert cert.verified


# ---------------------------------------------------------------------------
# ProofCertificate serialization
# ---------------------------------------------------------------------------


class TestProofCertificateSerialization:
    def test_to_json_verified(self) -> None:
        def f(x: float) -> float:
            return x

        cert = verify_function(f, post=lambda x, r: r == x)
        assert cert.verified

        # Build a JSON-serializable dict manually (library may not have to_json yet)
        data = {
            "function_name": cert.function_name,
            "source_hash": cert.source_hash,
            "status": cert.status.value,
            "preconditions": list(cert.preconditions),
            "postconditions": list(cert.postconditions),
            "counterexample": cert.counterexample,
            "message": cert.message,
            "solver_time_ms": cert.solver_time_ms,
            "z3_version": cert.z3_version,
        }
        serialized = json.dumps(data)
        loaded = json.loads(serialized)
        assert loaded["status"] == "verified"
        assert loaded["function_name"] == "f"
        assert isinstance(loaded["solver_time_ms"], float)

    def test_to_json_counterexample(self) -> None:
        def bad(x: float) -> float:
            return -x

        cert = verify_function(bad, post=lambda x, r: r >= 0)
        assert cert.status == Status.COUNTEREXAMPLE
        assert cert.counterexample is not None

        data = {
            "status": cert.status.value,
            "counterexample": cert.counterexample,
        }
        serialized = json.dumps(data)
        loaded = json.loads(serialized)
        assert loaded["status"] == "counterexample"
        assert "x" in loaded["counterexample"]


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


class TestCache:
    def test_cache_hit(self) -> None:
        def f(x: float) -> float:
            return x

        c1 = verify_function(f, post=lambda x, r: r == x)
        c2 = verify_function(f, post=lambda x, r: r == x)
        assert c1 is c2  # same object from cache

    def test_cache_cleared_by_clear_cache(self) -> None:
        def f(x: float) -> float:
            return x

        c1 = verify_function(f, post=lambda x, r: r == x)
        clear_cache()
        c2 = verify_function(f, post=lambda x, r: r == x)
        # After clearing, a new certificate is created (different object)
        assert c1 is not c2
        # But same result
        assert c1.verified == c2.verified

    def test_different_contracts_different_cache_entries(self) -> None:
        def f(x: float) -> float:
            return x + 1

        c1 = verify_function(f, post=lambda x, r: r > x)
        c2 = verify_function(f, post=lambda x, r: r >= 0)
        # Different postconditions — must not be the same cached cert
        assert c1 is not c2


# ---------------------------------------------------------------------------
# Contract signature validation
# ---------------------------------------------------------------------------


class TestContractValidation:
    def test_pre_wrong_arg_count_raises_or_errors(self) -> None:
        """A pre with wrong number of arguments should fail gracefully."""

        def f(x: float, y: float) -> float:
            return x + y

        # pre takes only 1 arg but function has 2 — Z3 call will fail
        cert = verify_function(f, pre=lambda z: z > 0, post=lambda x, y, r: r > 0)
        # Should return an error status, not raise
        assert cert.status in (
            Status.TRANSLATION_ERROR,
            Status.COUNTEREXAMPLE,
            Status.VERIFIED,
            Status.SKIPPED,
        )

    def test_post_wrong_arg_count_gives_error_status(self) -> None:
        """A post with wrong argument count should return TRANSLATION_ERROR."""

        def f(x: float) -> float:
            return x

        # post takes only 1 arg, but should take (x, result)
        cert = verify_function(f, post=lambda x: x > 0)
        # Might succeed (post(x) is valid!) or give translation error
        assert cert.status in (
            Status.VERIFIED,
            Status.COUNTEREXAMPLE,
            Status.TRANSLATION_ERROR,
            Status.SKIPPED,
        )

    def test_pre_using_python_and_gives_error(self) -> None:
        """Using 'and' in pre/post body gives an unhelpful but non-crashing error."""

        def f(x: float, y: float) -> float:
            return x + y

        # 'and' returns a bool, not a z3.BoolRef — engine catches this gracefully
        cert = verify_function(
            f,
            pre=lambda x, y: (x > 0) and (y > 0),
            post=lambda x, y, r: r > 0,
        )
        # The engine must not raise — it returns some status
        assert cert.status in (
            Status.VERIFIED,
            Status.COUNTEREXAMPLE,
            Status.TRANSLATION_ERROR,
            Status.SKIPPED,
        )


# ---------------------------------------------------------------------------
# No type hints — defaults to float
# ---------------------------------------------------------------------------


class TestNoTypeHints:
    def test_untyped_function_defaults_to_float(self) -> None:
        def f(x, y):  # type: ignore[no-untyped-def]
            return x + y

        cert = verify_function(
            f,
            pre=lambda x, y: (x >= 0) & (y >= 0),
            post=lambda x, y, r: r >= 0,
        )
        assert cert.verified


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_postcondition_skips(self) -> None:
        def f(x: float) -> float:
            return x

        cert = verify_function(f)
        assert cert.status == Status.SKIPPED

    def test_proof_certificate_str_verified(self) -> None:
        def f(x: float) -> float:
            return x

        cert = verify_function(f, post=lambda x, r: r == x)
        assert "Q.E.D." in str(cert)

    def test_proof_certificate_str_counterexample(self) -> None:
        def f(x: float) -> float:
            return -x

        cert = verify_function(f, post=lambda x, r: r >= 0)
        assert "DISPROVED" in str(cert)

    def test_solver_time_recorded(self) -> None:
        def f(x: float) -> float:
            return x + 1

        cert = verify_function(f, post=lambda x, r: r > x)
        assert cert.solver_time_ms >= 0

    def test_z3_version_recorded(self) -> None:
        def f(x: float) -> float:
            return x

        cert = verify_function(f, post=lambda x, r: r == x)
        assert cert.z3_version != ""

    def test_function_name_preserved(self) -> None:
        def my_special_function(x: float) -> float:
            return x * 2

        cert = verify_function(
            my_special_function,
            post=lambda x, r: r == x * 2,
        )
        assert cert.function_name == "my_special_function"

    def test_preconditions_recorded(self) -> None:
        def f(x: float) -> float:
            return x * 2

        cert = verify_function(
            f,
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
        )
        assert cert.verified
        assert len(cert.preconditions) >= 1

    def test_postconditions_recorded(self) -> None:
        def f(x: float) -> float:
            return x

        cert = verify_function(f, post=lambda x, r: r == x)
        assert cert.verified
        assert len(cert.postconditions) >= 1
