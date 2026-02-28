"""Full coverage of @runtime_checked decorator."""

from __future__ import annotations

import asyncio
import logging

import pytest

from provably.decorators import (
    ContractViolationError,
    runtime_checked,
)


# ---------------------------------------------------------------------------
# Pre-condition violation
# ---------------------------------------------------------------------------


class TestPreConditionViolation:
    def test_pre_violation_raises(self) -> None:
        @runtime_checked(pre=lambda x: x >= 0)
        def sqrt_floor(x: float) -> float:
            return x ** 0.5

        with pytest.raises(ContractViolationError) as exc_info:
            sqrt_floor(-1.0)

        err = exc_info.value
        assert err.kind == "pre"
        assert err.func_name == "sqrt_floor"
        assert err.args_ == (-1.0,)

    def test_pre_violation_error_attributes(self) -> None:
        @runtime_checked(pre=lambda x: x > 0, raise_on_failure=True)
        def positive_only(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError) as exc_info:
            positive_only(0.0)

        err = exc_info.value
        assert err.kind == "pre"
        assert err.result is None  # not set for pre violations

    def test_pre_with_multiple_args(self) -> None:
        @runtime_checked(pre=lambda a, b: a < b)
        def ordered_sum(a: float, b: float) -> float:
            return a + b

        # pre passes
        assert ordered_sum(1.0, 2.0) == 3.0

        # pre fails
        with pytest.raises(ContractViolationError) as exc_info:
            ordered_sum(5.0, 3.0)

        err = exc_info.value
        assert err.kind == "pre"
        assert err.args_ == (5.0, 3.0)

    def test_exception_in_pre_treated_as_failure(self) -> None:
        def bad_pre(x: float) -> bool:
            raise ValueError("pre exploded")

        @runtime_checked(pre=bad_pre, raise_on_failure=True)
        def f(x: float) -> float:
            return x

        # Exception in pre is caught and treated as False
        with pytest.raises(ContractViolationError):
            f(1.0)


# ---------------------------------------------------------------------------
# Post-condition violation
# ---------------------------------------------------------------------------


class TestPostConditionViolation:
    def test_post_violation_raises(self) -> None:
        @runtime_checked(post=lambda x, result: result >= 0)
        def broken_abs(x: float) -> float:
            return x  # wrong — doesn't negate

        with pytest.raises(ContractViolationError) as exc_info:
            broken_abs(-5.0)

        err = exc_info.value
        assert err.kind == "post"
        assert err.func_name == "broken_abs"
        assert err.result == -5.0

    def test_post_receives_return_value(self) -> None:
        captured = {}

        def capture_post(x: float, result: float) -> bool:
            captured["x"] = x
            captured["result"] = result
            return result >= 0

        @runtime_checked(post=capture_post)
        def double(x: float) -> float:
            return x * 2

        double(3.0)
        assert captured["x"] == 3.0
        assert captured["result"] == 6.0

    def test_exception_in_post_treated_as_failure(self) -> None:
        def bad_post(x: float, result: float) -> bool:
            raise RuntimeError("post exploded")

        @runtime_checked(post=bad_post, raise_on_failure=True)
        def f(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError):
            f(1.0)

    def test_post_violation_error_has_result(self) -> None:
        @runtime_checked(post=lambda x, result: result > 100)
        def f(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError) as exc_info:
            f(5.0)

        assert exc_info.value.result == 5.0
        assert exc_info.value.kind == "post"


# ---------------------------------------------------------------------------
# Both pass
# ---------------------------------------------------------------------------


class TestBothPass:
    def test_both_pass(self) -> None:
        @runtime_checked(
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= x,
        )
        def double(x: float) -> float:
            return x * 2

        result = double(3.0)
        assert result == 6.0

    def test_no_contracts_passthrough(self) -> None:
        @runtime_checked()
        def f(x: float) -> float:
            return x * 3

        assert f(4.0) == 12.0

    def test_bare_decorator(self) -> None:
        @runtime_checked
        def g(x: float) -> float:
            return x + 1

        assert g(5.0) == 6.0


# ---------------------------------------------------------------------------
# raise_on_failure=False — should log, not raise
# ---------------------------------------------------------------------------


class TestRaiseOnFailureFalse:
    def test_raise_on_failure_false_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        @runtime_checked(pre=lambda x: x >= 0, raise_on_failure=False)
        def f(x: float) -> float:
            return x

        with caplog.at_level(logging.WARNING, logger="provably"):
            result = f(-1.0)  # pre fails, but should not raise

        # Function still returns (pre violation logged, not raised)
        assert result == -1.0
        assert any("Contract violation" in r.message for r in caplog.records)

    def test_raise_on_failure_false_post_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        @runtime_checked(post=lambda x, result: result > 0, raise_on_failure=False)
        def f(x: float) -> float:
            return -x  # will violate post for positive x

        with caplog.at_level(logging.WARNING, logger="provably"):
            result = f(5.0)  # post returns -5 < 0, violation logged not raised

        assert result == -5.0
        assert any("Contract violation" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# ContractViolationError attributes and str
# ---------------------------------------------------------------------------


class TestContractViolationError:
    def test_contract_violation_error_attributes(self) -> None:
        err = ContractViolationError("pre", "my_func", (1, 2, 3))
        assert err.kind == "pre"
        assert err.func_name == "my_func"
        assert err.args_ == (1, 2, 3)
        assert err.result is None

    def test_contract_violation_error_post_attributes(self) -> None:
        err = ContractViolationError("post", "my_func", (1,), result=42)
        assert err.kind == "post"
        assert err.result == 42

    def test_contract_violation_error_str_pre(self) -> None:
        err = ContractViolationError("pre", "my_func", (5,))
        msg = str(err)
        assert "Precondition" in msg
        assert "my_func" in msg
        assert "5" in msg

    def test_contract_violation_error_str_post(self) -> None:
        err = ContractViolationError("post", "my_func", (5,), result=99)
        msg = str(err)
        assert "Postcondition" in msg
        assert "my_func" in msg
        assert "99" in msg


# ---------------------------------------------------------------------------
# Function metadata preservation
# ---------------------------------------------------------------------------


class TestFunctionMetadata:
    def test_preserves_function_name_and_doc(self) -> None:
        @runtime_checked(pre=lambda x: x > 0)
        def my_documented_function(x: float) -> float:
            """My documented function."""
            return x * 2

        assert my_documented_function.__name__ == "my_documented_function"
        assert my_documented_function.__doc__ == "My documented function."


# ---------------------------------------------------------------------------
# Async functions
# ---------------------------------------------------------------------------


class TestAsyncRuntimeChecked:
    def test_runtime_checked_on_async_function(self) -> None:
        @runtime_checked(
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= x,
        )
        async def async_double(x: float) -> float:
            return x * 2

        result = asyncio.get_event_loop().run_until_complete(async_double(3.0))
        assert result == 6.0

    def test_async_pre_violation_raises(self) -> None:
        @runtime_checked(pre=lambda x: x >= 0, raise_on_failure=True)
        async def async_fn(x: float) -> float:
            return x

        async def run():
            return await async_fn(-1.0)

        with pytest.raises(ContractViolationError):
            asyncio.get_event_loop().run_until_complete(run())

    def test_async_post_violation_raises(self) -> None:
        @runtime_checked(post=lambda x, result: result > 0, raise_on_failure=True)
        async def async_fn(x: float) -> float:
            return -x  # violates post for positive x

        async def run():
            return await async_fn(5.0)

        with pytest.raises(ContractViolationError):
            asyncio.get_event_loop().run_until_complete(run())


# ---------------------------------------------------------------------------
# @verified with check_contracts=True
# ---------------------------------------------------------------------------


class TestVerifiedWithCheckContracts:
    def test_check_contracts_on_verified(self) -> None:
        """@verified(check_contracts=True) adds runtime checking on top of static proof."""
        from conftest import requires_z3
        pytest.importorskip("z3")

        from provably.decorators import verified

        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= 0,
            check_contracts=True,
        )
        def nonneg_double(x: float) -> float:
            return x * 2

        # Correct call works
        assert nonneg_double(3.0) == 6.0

        # Pre violation raises at runtime
        with pytest.raises(ContractViolationError):
            nonneg_double(-1.0)

    def test_stacking_verified_and_runtime_checked(self) -> None:
        """Stack @runtime_checked on top of @verified for extra defence-in-depth."""
        pytest.importorskip("z3")

        from provably.decorators import verified

        @runtime_checked(
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= 0,
        )
        @verified(post=lambda x, result: result >= 0)
        def double_guarded(x: float) -> float:
            return x * 2

        assert double_guarded(4.0) == 8.0

        with pytest.raises(ContractViolationError):
            double_guarded(-1.0)
