"""The @verified decorator — proof-carrying Python functions.

Usage::

    from provably import verified
    from provably.types import Ge
    from typing import Annotated

    # Bare decorator — proves refinement type annotations
    @verified
    def double(x: Annotated[float, Ge(0)]) -> Annotated[float, Ge(0)]:
        return x * 2

    # With explicit pre/post contracts
    @verified(
        pre=lambda x, lo, hi: lo <= hi,
        post=lambda x, lo, hi, result: (result >= lo) & (result <= hi),
    )
    def clamp(x: float, lo: float, hi: float) -> float:
        if x < lo:
            return lo
        elif x > hi:
            return hi
        else:
            return x

    # Access proof certificate
    clamp.__proof__  # ProofCertificate

    # Runtime-only checking (no Z3 required)
    @runtime_checked(
        pre=lambda x: x >= 0,
        post=lambda x, result: result >= 0,
    )
    def sqrt_approx(x: float) -> float:
        return x ** 0.5

Note: In pre/post lambdas for @verified, use & instead of 'and',
      | instead of 'or', ~ instead of 'not'. Python's boolean operators
      cannot be overloaded and will not produce Z3 expressions.
"""

from __future__ import annotations

import functools
import inspect
import logging
import warnings
from collections.abc import Callable
from typing import Any, TypeVar, overload

from .engine import ProofCertificate, Status, _config, verify_function

logger = logging.getLogger("provably")

F = TypeVar("F", bound=Callable[..., Any])


class VerificationError(Exception):
    """Raised when ``raise_on_failure=True`` and verification fails.

    The failing :class:`~provably.engine.ProofCertificate` is available
    as ``exc.certificate``.
    """

    def __init__(self, certificate: ProofCertificate) -> None:
        self.certificate = certificate
        super().__init__(str(certificate))


class ContractViolationError(Exception):
    """Raised by :func:`runtime_checked` when a contract is violated at runtime.

    Attributes:
        kind: ``"pre"`` or ``"post"``.
        args_: The positional arguments that triggered the violation.
        result: The return value (only set when ``kind == "post"``).
    """

    def __init__(
        self,
        kind: str,
        func_name: str,
        args_: tuple[Any, ...],
        result: Any = None,
    ) -> None:
        self.kind = kind
        self.func_name = func_name
        self.args_ = args_
        self.result = result
        if kind == "pre":
            msg = f"Precondition violated for '{func_name}' with args {args_}"
        else:
            msg = f"Postcondition violated for '{func_name}' with args {args_}, result={result!r}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Runtime contract validation helpers
# ---------------------------------------------------------------------------


def _check_contract_arity(
    fn: Callable[..., Any],
    expected: int,
    label: str,
    fname: str,
) -> None:
    """Warn if a contract callable has the wrong arity.

    Args:
        fn: The pre or post callable.
        expected: Expected number of positional arguments.
        label: ``"pre"`` or ``"post"`` (for the warning message).
        fname: Name of the decorated function.
    """
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return

    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
    if has_varargs:
        return

    params = [
        p
        for p in sig.parameters.values()
        if p.kind
        not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    ]
    if len(params) != expected:
        warnings.warn(
            f"{label} contract for '{fname}' takes {len(params)} argument(s),"
            f" expected {expected}. The contract may not be called correctly.",
            stacklevel=4,
        )


# ---------------------------------------------------------------------------
# @verified decorator
# ---------------------------------------------------------------------------


@overload
def verified(func: F) -> F: ...


@overload
def verified(
    *,
    pre: Callable[..., Any] | None = ...,
    post: Callable[..., Any] | None = ...,
    raise_on_failure: bool = ...,
    strict: bool = ...,
    timeout_ms: int = ...,
    contracts: dict[str, dict[str, Any]] | None = ...,
    check_contracts: bool = ...,
) -> Callable[[F], F]: ...


def verified(
    func: F | None = None,
    *,
    pre: Callable[..., Any] | None = None,
    post: Callable[..., Any] | None = None,
    raise_on_failure: bool | None = None,
    strict: bool | None = None,
    timeout_ms: int | None = None,
    contracts: dict[str, dict[str, Any]] | None = None,
    check_contracts: bool = False,
) -> F | Callable[[F], F]:
    """Decorator that formally verifies a Python function using Z3.

    Args:
        func: The function (when used as bare ``@verified``).
        pre: Precondition lambda — takes the same arguments as *func*.
            Use ``&`` / ``|`` / ``~`` instead of ``and`` / ``or`` / ``not``
            to stay in Z3 expression space.
        post: Postcondition lambda — takes ``(*args, result)``.
        raise_on_failure: If ``True``, raise :class:`VerificationError` when
            the proof fails.  Defaults to the global setting (``False``).
        strict: Deprecated alias for *raise_on_failure*.  Will be removed in
            a future version.
        timeout_ms: Z3 solver timeout in milliseconds.  Defaults to the
            global setting (5000ms).
        contracts: Pre/post contracts of functions called inside *func*,
            keyed by function name.  Enables modular verification.
        check_contracts: If ``True``, the wrapper also performs a runtime
            pre/post check on every call (in addition to the static Z3 proof).
            Useful as a defence-in-depth measure for functions whose proof
            is SKIPPED or UNKNOWN.

    Returns:
        The original function, unchanged at runtime, with a
        :class:`~provably.engine.ProofCertificate` attached as
        ``func.__proof__``.

    The decorated function is identical to the original — no overhead is
    added to call sites (unless ``check_contracts=True``).

    Async functions are not translated (Z3 does not support coroutine bodies).
    They receive a ``SKIPPED`` certificate and the wrapper is a passthrough.
    """
    # Handle deprecated 'strict' parameter
    if strict is not None:
        warnings.warn(
            "The 'strict' parameter is deprecated. Use 'raise_on_failure' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if raise_on_failure is None:
            raise_on_failure = strict

    # Fall back to global config
    if raise_on_failure is None:
        raise_on_failure = bool(_config.get("raise_on_failure", False))
    if timeout_ms is None:
        timeout_ms = int(_config.get("timeout_ms", 5000))

    if func is not None:
        # Bare @verified usage
        return _verify_and_wrap(
            func, pre, post, raise_on_failure, timeout_ms, contracts, check_contracts
        )

    # @verified(...) usage — return a decorator
    def decorator(fn: F) -> F:
        return _verify_and_wrap(
            fn, pre, post, raise_on_failure, timeout_ms, contracts, check_contracts
        )

    return decorator  # type: ignore[return-value]


def _verify_and_wrap(
    func: F,
    pre: Callable[..., Any] | None,
    post: Callable[..., Any] | None,
    raise_on_failure: bool,
    timeout_ms: int,
    contracts: dict[str, dict[str, Any]] | None,
    check_contracts: bool,
) -> F:
    """Run verification and attach the certificate."""
    fname = getattr(func, "__name__", str(func))

    # Async functions: skip translation, attach SKIPPED certificate
    if inspect.iscoroutinefunction(func):
        cert = ProofCertificate(
            function_name=fname,
            source_hash="",
            status=Status.SKIPPED,
            preconditions=(),
            postconditions=(),
            message="async functions are not supported by the Z3 translator",
        )
        logger.debug("SKIPPED (async) %s", fname)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
            return await func(*args, **kwargs)

        async_wrapper.__proof__ = cert  # type: ignore[attr-defined]
        async_wrapper.__contract__ = {  # type: ignore[attr-defined]
            "pre": pre,
            "post": post,
            "verified": False,
        }
        return async_wrapper  # type: ignore[return-value]

    # Validate contract arities before calling the engine
    try:
        n_params = len(inspect.signature(func).parameters)
    except (ValueError, TypeError):
        n_params = 0

    if pre is not None:
        _check_contract_arity(pre, n_params, "pre", fname)
    if post is not None:
        _check_contract_arity(post, n_params + 1, "post", fname)

    cert = verify_function(
        func,
        pre=pre,
        post=post,
        timeout_ms=timeout_ms,
        verified_contracts=contracts,
    )

    if cert.verified:
        logger.debug("Q.E.D. %s (%.1fms)", fname, cert.solver_time_ms)
    elif cert.status == Status.COUNTEREXAMPLE:
        msg = f"DISPROVED {fname}: {cert.counterexample}"
        logger.warning(msg)
        if raise_on_failure:
            raise VerificationError(cert)
    elif cert.status == Status.UNKNOWN:
        logger.info("UNKNOWN %s (timeout?)", fname)
    elif cert.status == Status.TRANSLATION_ERROR:
        logger.info("TRANSLATION_ERROR %s: %s", fname, cert.message)
    else:
        logger.debug("SKIPPED %s: %s", fname, cert.message)

    if check_contracts and (pre is not None or post is not None):
        # Build a runtime-checking wrapper
        @functools.wraps(func)
        def checked_wrapper(*args: Any, **kwargs: Any) -> Any:
            if pre is not None:
                try:
                    ok = pre(*args)
                except Exception:
                    ok = False
                if not ok:
                    raise ContractViolationError("pre", fname, args)
            result = func(*args, **kwargs)
            if post is not None:
                try:
                    ok = post(*args, result)
                except Exception:
                    ok = False
                if not ok:
                    raise ContractViolationError("post", fname, args, result)
            return result

        checked_wrapper.__proof__ = cert  # type: ignore[attr-defined]
        checked_wrapper.__contract__ = {  # type: ignore[attr-defined]
            "pre": pre,
            "post": post,
            "verified": cert.verified,
        }
        return checked_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    wrapper.__proof__ = cert  # type: ignore[attr-defined]

    # Export contract for compositionality — other @verified functions
    # calling this one can use its pre/post as assumptions.
    wrapper.__contract__ = {  # type: ignore[attr-defined]
        "pre": pre,
        "post": post,
        "verified": cert.verified,
    }

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# @runtime_checked decorator
# ---------------------------------------------------------------------------


def runtime_checked(
    func: F | None = None,
    *,
    pre: Callable[..., Any] | None = None,
    post: Callable[..., Any] | None = None,
    raise_on_failure: bool = True,
) -> F | Callable[[F], F]:
    """Decorator that checks pre/post contracts at runtime without Z3.

    Unlike :func:`verified`, this decorator does not perform a static proof.
    It simply evaluates the pre and post conditions on every actual call and
    raises :class:`ContractViolationError` when one fails.

    This is useful when:

    - You want zero solver overhead at runtime.
    - The function body uses constructs the translator does not support.
    - You want defence-in-depth in addition to a static proof.

    Args:
        func: The function (when used as bare ``@runtime_checked``).
        pre: Precondition callable — takes the same arguments as *func*.
            Must return a truthy value when the precondition holds.
        post: Postcondition callable — takes ``(*args, result)``.
            Must return a truthy value when the postcondition holds.
        raise_on_failure: If ``True`` (default), raise
            :class:`ContractViolationError` on violation.  If ``False``,
            log a warning instead.

    Returns:
        The wrapped function.  Identical to the original at call sites
        when all contracts pass.

    Example::

        @runtime_checked(
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= 0,
        )
        def sqrt_approx(x: float) -> float:
            return x ** 0.5
    """
    if func is not None:
        return _runtime_wrap(func, pre, post, raise_on_failure)

    def decorator(fn: F) -> F:
        return _runtime_wrap(fn, pre, post, raise_on_failure)

    return decorator  # type: ignore[return-value]


def _runtime_wrap(
    func: F,
    pre: Callable[..., Any] | None,
    post: Callable[..., Any] | None,
    raise_on_failure: bool,
) -> F:
    fname = getattr(func, "__name__", str(func))

    try:
        n_params = len(inspect.signature(func).parameters)
    except (ValueError, TypeError):
        n_params = 0

    if pre is not None:
        _check_contract_arity(pre, n_params, "pre", fname)
    if post is not None:
        _check_contract_arity(post, n_params + 1, "post", fname)

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_checked_wrapper(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
            if pre is not None:
                try:
                    ok = pre(*args)
                except Exception:
                    ok = False
                if not ok:
                    _handle_violation(
                        ContractViolationError("pre", fname, args),
                        raise_on_failure,
                    )
            result = await func(*args, **kwargs)
            if post is not None:
                try:
                    ok = post(*args, result)
                except Exception:
                    ok = False
                if not ok:
                    _handle_violation(
                        ContractViolationError("post", fname, args, result),
                        raise_on_failure,
                    )
            return result

        return async_checked_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def checked_wrapper(*args: Any, **kwargs: Any) -> Any:
        if pre is not None:
            try:
                ok = pre(*args)
            except Exception:
                ok = False
            if not ok:
                _handle_violation(
                    ContractViolationError("pre", fname, args),
                    raise_on_failure,
                )
        result = func(*args, **kwargs)
        if post is not None:
            try:
                ok = post(*args, result)
            except Exception:
                ok = False
            if not ok:
                _handle_violation(
                    ContractViolationError("post", fname, args, result),
                    raise_on_failure,
                )
        return result

    return checked_wrapper  # type: ignore[return-value]


def _handle_violation(exc: ContractViolationError, raise_on_failure: bool) -> None:
    if raise_on_failure:
        raise exc
    logger.warning("Contract violation: %s", exc)
