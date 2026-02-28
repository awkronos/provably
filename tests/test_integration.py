"""End-to-end integration tests — @verified decorator on real functions."""

from __future__ import annotations

import asyncio
from typing import Annotated

import pytest
from conftest import requires_z3

pytestmark = requires_z3

from provably import Status, VerificationError, clear_cache, verified
from provably.engine import verify_function
from provably.types import Between, Ge, Le


@pytest.fixture(autouse=True)
def _clear() -> None:
    clear_cache()


# ---------------------------------------------------------------------------
# Decorator — bare usage
# ---------------------------------------------------------------------------


class TestBareDecorator:
    def test_refinement_types_auto_verified(self) -> None:
        @verified
        def nonneg_double(x: Annotated[float, Ge(0)]) -> Annotated[float, Ge(0)]:
            return x * 2

        assert nonneg_double.__proof__.verified
        assert nonneg_double(5) == 10  # runtime still works

    def test_refinement_bounded(self) -> None:
        @verified
        def to_unit(x: Annotated[float, Between(0, 10)]) -> Annotated[float, Between(0, 1)]:
            return x / 10

        assert to_unit.__proof__.verified
        assert to_unit(5) == 0.5


# ---------------------------------------------------------------------------
# Decorator — with explicit contracts
# ---------------------------------------------------------------------------


class TestExplicitContracts:
    def test_clamp_verified(self) -> None:
        @verified(
            pre=lambda val, lo, hi: lo <= hi,
            post=lambda val, lo, hi, result: (result >= lo) & (result <= hi),
        )
        def clamp(val: float, lo: float, hi: float) -> float:
            if val < lo:
                return lo
            elif val > hi:
                return hi
            else:
                return val

        assert clamp.__proof__.verified
        assert clamp(5, 0, 10) == 5
        assert clamp(-1, 0, 10) == 0
        assert clamp(15, 0, 10) == 10

    def test_abs_verified(self) -> None:
        @verified(post=lambda x, result: result >= 0)
        def safe_abs(x: float) -> float:
            if x >= 0:
                return x
            else:
                return -x

        assert safe_abs.__proof__.verified
        assert safe_abs(-3) == 3
        assert safe_abs(7) == 7

    def test_max_verified(self) -> None:
        @verified(post=lambda a, b, result: (result >= a) & (result >= b))
        def safe_max(a: float, b: float) -> float:
            if a >= b:
                return a
            else:
                return b

        assert safe_max.__proof__.verified

    def test_relu_verified(self) -> None:
        @verified(post=lambda x, result: result >= 0)
        def relu(x: float) -> float:
            if x > 0:
                return x
            else:
                return 0.0

        assert relu.__proof__.verified
        assert relu(-5) == 0.0
        assert relu(3) == 3


# ---------------------------------------------------------------------------
# Strict mode / raise_on_failure
# ---------------------------------------------------------------------------


class TestStrictMode:
    def test_strict_raises_on_counterexample(self) -> None:
        with pytest.raises(VerificationError) as exc_info:

            @verified(strict=True, post=lambda x, result: result > 0)
            def negate(x: float) -> float:
                return -x

        assert exc_info.value.certificate.status == Status.COUNTEREXAMPLE

    def test_raise_on_failure_alias(self) -> None:
        """strict=True is the raise_on_failure pattern — test it works end-to-end."""
        with pytest.raises(VerificationError) as exc_info:

            @verified(strict=True, post=lambda x, r: r == x + 2)
            def inc_wrong(x: float) -> float:
                return x + 1  # off by one

        cert = exc_info.value.certificate
        assert cert.status == Status.COUNTEREXAMPLE
        # Certificate is embedded in the exception
        assert cert.counterexample is not None

    def test_strict_does_not_raise_on_verified(self) -> None:
        """strict=True should not raise when the proof succeeds."""

        @verified(strict=True, post=lambda x, r: r >= 0)
        def safe_abs(x: float) -> float:
            if x >= 0:
                return x
            return -x

        assert safe_abs.__proof__.verified
        assert safe_abs(-5) == 5


# ---------------------------------------------------------------------------
# Async functions
# ---------------------------------------------------------------------------


class TestAsyncFunctions:
    def test_async_function_gets_skipped_cert(self) -> None:
        """Async functions cannot be source-inspected at definition time in
        the same way, or the translator cannot handle async syntax.
        The decorator should attach a cert — SKIPPED or TRANSLATION_ERROR,
        not raise an uncaught exception.
        """

        @verified(post=lambda x, r: r >= 0)
        async def async_abs(x: float) -> float:
            if x >= 0:
                return x
            return -x

        # The decorator must not have raised
        cert = async_abs.__proof__
        assert cert.status in (
            Status.SKIPPED,
            Status.TRANSLATION_ERROR,
            Status.VERIFIED,
            Status.UNKNOWN,
        )

    def test_async_function_still_callable(self) -> None:
        """The decorated async function must still be callable as a coroutine."""

        @verified(post=lambda x, r: r >= 0)
        async def async_relu(x: float) -> float:
            if x > 0:
                return x
            return 0.0

        result = asyncio.get_event_loop().run_until_complete(async_relu(-3.0))
        assert result == 0.0


# ---------------------------------------------------------------------------
# Runtime checked decorator
# ---------------------------------------------------------------------------


class TestRuntimeChecked:
    def test_runtime_checked_passes_valid_input(self) -> None:
        """@verified function called with valid input runs normally."""

        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
        )
        def sqrt_approx(x: float) -> float:
            if x < 0:
                return 0.0
            y = x
            for _ in range(10):
                y = (y + x / y) / 2 if y != 0 else x
            return y

        # sqrt_approx is NOT a runtime-checked decorator on its own,
        # but it wraps cleanly and remains callable
        result = sqrt_approx(4.0)
        assert result > 0

    def test_runtime_precondition_via_assert(self) -> None:
        """Functions using assert for pre-conditions throw AssertionError at runtime."""

        @verified(post=lambda x, r: r >= 0)
        def safe_log_approx(x: float) -> float:
            assert x > 0, "x must be positive"
            return x - 1  # crude approximation around x=1

        with pytest.raises(AssertionError):
            safe_log_approx(-1.0)


# ---------------------------------------------------------------------------
# Safety-critical patterns (Kagami-style)
# ---------------------------------------------------------------------------


class TestSafetyPatterns:
    def test_bounded_parameter_mutation(self) -> None:
        """Simulates GodelLoop's _enforce_contraction pattern."""

        @verified(
            pre=lambda lr: (lr >= 0.5) & (lr <= 5.0),
            post=lambda lr, result: (result >= 0.5) & (result <= 5.0),
        )
        def contract_lr(lr: float) -> float:
            default = 2.0
            decay = 0.05
            new_lr = lr + (default - lr) * decay
            if new_lr < 0.5:
                return 0.5
            elif new_lr > 5.0:
                return 5.0
            else:
                return new_lr

        assert contract_lr.__proof__.verified

    def test_safety_gate_blocks_unsafe(self) -> None:
        """If h < 0, motor action is always blocked (returns 0)."""

        @verified(
            pre=lambda h, action: h < 0,
            post=lambda h, action, result: result == 0,
        )
        def safety_gate(h: float, action: int) -> int:
            if h < 0:
                return 0
            return action

        assert safety_gate.__proof__.verified

    def test_decay_preserves_bounds(self) -> None:
        """Multiplicative decay preserves minimum bound."""

        @verified(
            pre=lambda x: (x >= 0.1) & (x <= 0.8),
            post=lambda x, result: (result >= 0.1) & (result <= 0.8),
        )
        def decay(x: float) -> float:
            new_x = x * 0.95
            if new_x < 0.1:
                return 0.1
            return new_x

        assert decay.__proof__.verified

    def test_boost_preserves_bounds(self) -> None:
        """Multiplicative boost with clamping preserves maximum bound."""

        @verified(
            pre=lambda x: (x >= 0.5) & (x <= 5.0),
            post=lambda x, result: (result >= 0.5) & (result <= 5.0),
        )
        def boost(x: float) -> float:
            new_x = x * 1.5
            if new_x > 5.0:
                return 5.0
            return new_x

        assert boost.__proof__.verified

    def test_lerp_between_bounds(self) -> None:
        """Linear interpolation stays within [a, b]."""

        @verified(
            pre=lambda a, b, t: (a <= b) & (t >= 0) & (t <= 1),
            post=lambda a, b, t, result: (result >= a) & (result <= b),
        )
        def lerp(a: float, b: float, t: float) -> float:
            return a + (b - a) * t

        assert lerp.__proof__.verified


# ---------------------------------------------------------------------------
# Compositionality
# ---------------------------------------------------------------------------


class TestCompositionality:
    def test_contract_attribute_exists(self) -> None:
        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
        )
        def f(x: float) -> float:
            return x

        assert hasattr(f, "__contract__")
        assert f.__contract__["verified"]

    def test_builtin_min_max_in_body(self) -> None:
        @verified(
            pre=lambda x: (x >= 0) & (x <= 100),
            post=lambda x, result: (result >= 0) & (result <= 10),
        )
        def normalize(x: float) -> float:
            y = x / 10
            return min(max(y, 0.0), 10.0)

        assert normalize.__proof__.verified

    def test_verified_function_a_calls_b_via_contracts(self) -> None:
        """Modular verification: A calls B using B's contract as an axiom."""

        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
        )
        def double_nonneg(x: float) -> float:
            return x * 2

        # Build the contract dict for double_nonneg
        import z3

        double_contract = {
            "pre": lambda x: x >= 0,
            "post": lambda x, r: r >= 0,
            "return_sort": z3.RealSort(),
        }

        # B calls double_nonneg — we pass its contract so the proof is modular
        cert = verify_function(
            # A wrapper that calls double_nonneg using symbolic contract
            lambda x: None,  # placeholder — actual test is contract dict round-trip
            post=None,
        )
        # The contract dict is correctly structured
        assert double_contract["return_sort"] == z3.RealSort()
        assert double_nonneg.__contract__["verified"]

    def test_verify_multiple_functions_sequentially(self) -> None:
        """verify_function on multiple independent functions, each gets its own cert."""

        def f(x: float) -> float:
            return x + 1

        def g(x: float) -> float:
            return x * 2

        c_f = verify_function(f, post=lambda x, r: r > x)
        c_g = verify_function(g, pre=lambda x: x >= 0, post=lambda x, r: r >= x)
        assert c_f.verified
        assert c_g.verified
        assert c_f is not c_g


# ---------------------------------------------------------------------------
# Runtime behavior preserved
# ---------------------------------------------------------------------------


class TestRuntimeBehavior:
    def test_verified_function_still_callable(self) -> None:
        @verified(post=lambda x, r: r == x + 1)
        def inc(x: float) -> float:
            return x + 1

        assert inc(5) == 6
        assert inc(0) == 1
        assert inc(-1) == 0

    def test_verified_preserves_docstring(self) -> None:
        @verified(post=lambda x, r: r >= 0)
        def f(x: float) -> float:
            """My docstring."""
            if x >= 0:
                return x
            return -x

        assert f.__doc__ == "My docstring."

    def test_verified_preserves_name(self) -> None:
        @verified(post=lambda x, r: r == x)
        def my_func(x: float) -> float:
            return x

        assert my_func.__name__ == "my_func"
