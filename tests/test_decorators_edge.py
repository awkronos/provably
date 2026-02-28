"""Decorator edge cases — @verified and @runtime_checked."""

from __future__ import annotations

import warnings

import pytest

from conftest import requires_z3

from provably.decorators import (
    ContractViolationError,
    VerificationError,
    runtime_checked,
    verified,
)
from provably.engine import Status, clear_cache, configure


# ---------------------------------------------------------------------------
# Async functions → SKIPPED
# ---------------------------------------------------------------------------


@requires_z3
def test_async_function_gets_skipped_cert() -> None:
    @verified(post=lambda x, result: result >= 0)
    async def async_fn(x: float) -> float:
        return x * 2

    proof = async_fn.__proof__
    assert proof.status == Status.SKIPPED
    assert "async" in proof.message.lower()


# ---------------------------------------------------------------------------
# Per-function timeout
# ---------------------------------------------------------------------------


@requires_z3
def test_per_function_timeout() -> None:
    """A 1ms timeout on a complex function should yield UNKNOWN (or VERIFIED on fast machines)."""
    @verified(timeout_ms=1, post=lambda x, result: result >= 0)
    def abs_val(x: float) -> float:
        if x >= 0:
            return x
        else:
            return -x

    proof = abs_val.__proof__
    # Fast machines may still solve within 1ms — accept both
    assert proof.status in (Status.UNKNOWN, Status.VERIFIED)


# ---------------------------------------------------------------------------
# raise_on_failure
# ---------------------------------------------------------------------------


@requires_z3
def test_raise_on_failure_true() -> None:
    """raise_on_failure=True raises VerificationError on counterexample."""
    with pytest.raises(VerificationError) as exc_info:
        @verified(raise_on_failure=True, post=lambda x, result: result > 0)
        def negate(x: float) -> float:
            return -x

    cert = exc_info.value.certificate
    assert cert.status == Status.COUNTEREXAMPLE


@requires_z3
def test_raise_on_failure_false_no_exception() -> None:
    """raise_on_failure=False (default) does not raise on counterexample."""
    # Should not raise — proof will DISPROVE but no exception
    @verified(raise_on_failure=False, post=lambda x, result: result > 0)
    def negate(x: float) -> float:
        return -x

    assert negate.__proof__.status == Status.COUNTEREXAMPLE


# ---------------------------------------------------------------------------
# strict deprecation warning
# ---------------------------------------------------------------------------


@requires_z3
def test_strict_emits_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @verified(strict=True, post=lambda x, result: result >= 0)
        def relu(x: float) -> float:
            if x >= 0:
                return x
            return 0.0

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep_warnings, "Expected a DeprecationWarning for 'strict' parameter"
    assert "strict" in str(dep_warnings[0].message).lower()


# ---------------------------------------------------------------------------
# No type hints — defaults to float
# ---------------------------------------------------------------------------


@requires_z3
def test_no_type_hints_defaults_to_float() -> None:
    @verified(post=lambda x, result: result == x)  # type: ignore[no-untyped-def]
    def identity(x):  # no annotations
        return x

    proof = identity.__proof__
    # Should verify — identity with float default
    assert proof.status in (Status.VERIFIED, Status.SKIPPED)


# ---------------------------------------------------------------------------
# ProofCertificate is frozen
# ---------------------------------------------------------------------------


@requires_z3
def test_proof_is_frozen() -> None:
    @verified(post=lambda x, result: result == x)
    def f(x: float) -> float:
        return x

    proof = f.__proof__
    with pytest.raises((AttributeError, TypeError)):
        proof.status = Status.UNKNOWN  # type: ignore[misc]


# ---------------------------------------------------------------------------
# __contract__ dict structure
# ---------------------------------------------------------------------------


@requires_z3
def test_contract_dict_structure() -> None:
    pre_fn = lambda x: x >= 0
    post_fn = lambda x, result: result >= 0

    @verified(pre=pre_fn, post=post_fn)
    def double(x: float) -> float:
        return x * 2

    contract = double.__contract__
    assert "pre" in contract
    assert "post" in contract
    assert "verified" in contract
    assert contract["pre"] is pre_fn
    assert contract["post"] is post_fn
    assert isinstance(contract["verified"], bool)


# ---------------------------------------------------------------------------
# configure() affects timeout and raise_on_failure
# ---------------------------------------------------------------------------


@requires_z3
def test_configure_affects_timeout() -> None:
    """configure(timeout_ms=1) is used when no per-call override is given."""
    configure(timeout_ms=1)
    try:
        @verified(post=lambda x, result: result >= 0)
        def abs_val(x: float) -> float:
            if x >= 0:
                return x
            else:
                return -x

        proof = abs_val.__proof__
        # 1ms timeout: UNKNOWN or VERIFIED (fast machines)
        assert proof.status in (Status.UNKNOWN, Status.VERIFIED)
    finally:
        configure(timeout_ms=5000)  # restore default


@requires_z3
def test_configure_affects_raise_on_failure() -> None:
    """configure(raise_on_failure=True) causes decorator to raise on disproof."""
    configure(raise_on_failure=True)
    try:
        with pytest.raises(VerificationError):
            @verified(post=lambda x, result: result > 0)
            def bad(x: float) -> float:
                return -x
    finally:
        configure(raise_on_failure=False)  # restore default


# ---------------------------------------------------------------------------
# Docstring doesn't break verification
# ---------------------------------------------------------------------------


@requires_z3
def test_verified_with_docstring() -> None:
    @verified(post=lambda x, result: result == x * 2)
    def double(x: float) -> float:
        """Double x."""
        return x * 2

    assert double.__proof__.verified


# ---------------------------------------------------------------------------
# Decorated function returns same value
# ---------------------------------------------------------------------------


@requires_z3
def test_verified_preserves_return_value() -> None:
    @verified(post=lambda x, result: result >= 0)
    def relu(x: float) -> float:
        if x >= 0:
            return x
        else:
            return 0.0

    assert relu(5.0) == 5.0
    assert relu(-3.0) == 0.0
    assert relu(0.0) == 0.0


# ---------------------------------------------------------------------------
# Async __contract__ structure
# ---------------------------------------------------------------------------


@requires_z3
def test_async_contract_dict_structure() -> None:
    """Async functions also get __contract__ attached."""
    @verified(pre=lambda x: x >= 0)
    async def async_fn(x: float) -> float:
        return x

    contract = async_fn.__contract__
    assert "pre" in contract
    assert "post" in contract
    assert "verified" in contract
    assert contract["verified"] is False  # async is always SKIPPED


# ---------------------------------------------------------------------------
# VerificationError carries certificate
# ---------------------------------------------------------------------------


@requires_z3
def test_verification_error_carries_certificate() -> None:
    with pytest.raises(VerificationError) as exc_info:
        @verified(raise_on_failure=True, post=lambda x, result: result > 100)
        def f(x: float) -> float:
            return x

    err = exc_info.value
    assert hasattr(err, "certificate")
    assert err.certificate.status == Status.COUNTEREXAMPLE
    assert str(err)  # should have a non-empty string representation
