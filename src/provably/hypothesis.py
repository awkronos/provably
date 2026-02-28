"""Bridge between provably's Z3 verification and Hypothesis property testing.

Install: pip install provably[hypothesis]

This module provides:
- ``from_refinements`` — generate Hypothesis strategies from Annotated types
- ``from_counterexample`` — extract argument dict from a ProofCertificate
- ``hypothesis_check`` — run Hypothesis as a Z3 fallback
- ``proven_property`` — decorator that tries Z3 first, falls back to Hypothesis

All hypothesis imports are lazy so this module is importable without
hypothesis installed (raises ImportError with an install hint on use).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from .engine import ProofCertificate, Status, verify_function
from .types import Between, Ge, Gt, Le, Lt, NotEq

if TYPE_CHECKING:
    pass


def _require_hypothesis() -> Any:
    """Import and return hypothesis.strategies, raising a helpful error if missing."""
    try:
        from hypothesis import strategies

        return strategies
    except ImportError as exc:
        raise ImportError(
            "hypothesis is required for this feature. "
            "Install it with: pip install provably[hypothesis]"
        ) from exc


# ---------------------------------------------------------------------------
# from_refinements
# ---------------------------------------------------------------------------


def from_refinements(typ: type) -> Any:
    """Build a Hypothesis strategy from an Annotated type with refinement markers.

    Args:
        typ: A Python type, optionally ``Annotated[base, *markers]``.
            Supported base types: ``int``, ``float``, ``bool``.
            Supported markers: :class:`~provably.types.Gt`,
            :class:`~provably.types.Ge`, :class:`~provably.types.Lt`,
            :class:`~provably.types.Le`, :class:`~provably.types.Between`,
            :class:`~provably.types.NotEq`.

    Returns:
        A ``hypothesis.strategies`` strategy.

    Raises:
        TypeError: If the base type is not ``int``, ``float``, or ``bool``.
        ImportError: If hypothesis is not installed.

    Example::

        from typing import Annotated
        from provably.types import Ge, Le
        from provably.hypothesis import from_refinements

        strategy = from_refinements(Annotated[int, Ge(0), Le(100)])
        # Draws integers in [0, 100]
    """
    st = _require_hypothesis()

    origin = get_origin(typ)
    if origin is Annotated:
        args = get_args(typ)
        base = args[0]
        markers = args[1:]
    else:
        base = typ
        markers = ()

    # Resolve nested Annotated base types
    while get_origin(base) is Annotated:
        inner_args = get_args(base)
        markers = inner_args[1:] + tuple(markers)
        base = inner_args[0]

    if base is bool:
        return st.booleans()
    elif base is int:
        return _int_strategy(st, markers)
    elif base is float:
        return _float_strategy(st, markers)
    else:
        raise TypeError(
            f"Unsupported base type for from_refinements: {base!r}. Supported: int, float, bool."
        )


def _int_strategy(st: Any, markers: tuple[Any, ...]) -> Any:
    """Build an integer strategy from refinement markers."""
    min_value: int | None = None
    max_value: int | None = None
    filters: list[Any] = []

    for marker in markers:
        if isinstance(marker, Gt):
            bound = int(marker.bound) + 1 if isinstance(marker.bound, int) else None
            if bound is not None:
                min_value = max(min_value, bound) if min_value is not None else bound
            else:
                # float bound — use filter
                b = marker.bound
                filters.append(lambda x, b=b: x > b)
        elif isinstance(marker, Ge):
            bound = int(marker.bound) if isinstance(marker.bound, (int, float)) else None
            if bound is not None:
                b_int = int(marker.bound)
                min_value = max(min_value, b_int) if min_value is not None else b_int
        elif isinstance(marker, Lt):
            bound = int(marker.bound) - 1 if isinstance(marker.bound, int) else None
            if bound is not None:
                max_value = min(max_value, bound) if max_value is not None else bound
            else:
                b = marker.bound
                filters.append(lambda x, b=b: x < b)
        elif isinstance(marker, Le):
            b_int = int(marker.bound)
            max_value = min(max_value, b_int) if max_value is not None else b_int
        elif isinstance(marker, Between):
            lo = int(marker.lo)
            hi = int(marker.hi)
            min_value = max(min_value, lo) if min_value is not None else lo
            max_value = min(max_value, hi) if max_value is not None else hi
        elif isinstance(marker, NotEq):
            v = marker.val
            filters.append(lambda x, v=v: x != v)

    strategy = st.integers(min_value=min_value, max_value=max_value)
    for f in filters:
        strategy = strategy.filter(f)
    return strategy


def _float_strategy(st: Any, markers: tuple[Any, ...]) -> Any:
    """Build a float strategy from refinement markers."""
    kwargs: dict[str, Any] = {
        "allow_nan": False,
        "allow_infinity": False,
    }
    filters: list[Any] = []

    for marker in markers:
        if isinstance(marker, Gt):
            b = marker.bound
            current_min = kwargs.get("min_value")
            if current_min is None or b >= current_min:
                kwargs["min_value"] = b
                kwargs["exclude_min"] = True
            else:
                filters.append(lambda x, b=b: x > b)
        elif isinstance(marker, Ge):
            b = marker.bound
            current_min = kwargs.get("min_value")
            if current_min is None or b > current_min:
                kwargs["min_value"] = b
                kwargs.pop("exclude_min", None)
            elif b == current_min:
                kwargs.pop("exclude_min", None)
        elif isinstance(marker, Lt):
            b = marker.bound
            current_max = kwargs.get("max_value")
            if current_max is None or b <= current_max:
                kwargs["max_value"] = b
                kwargs["exclude_max"] = True
            else:
                filters.append(lambda x, b=b: x < b)
        elif isinstance(marker, Le):
            b = marker.bound
            current_max = kwargs.get("max_value")
            if current_max is None or b < current_max:
                kwargs["max_value"] = b
                kwargs.pop("exclude_max", None)
            elif b == current_max:
                kwargs.pop("exclude_max", None)
        elif isinstance(marker, Between):
            lo, hi = marker.lo, marker.hi
            current_min = kwargs.get("min_value")
            current_max = kwargs.get("max_value")
            if current_min is None or lo > current_min:
                kwargs["min_value"] = lo
                kwargs.pop("exclude_min", None)
            if current_max is None or hi < current_max:
                kwargs["max_value"] = hi
                kwargs.pop("exclude_max", None)
        elif isinstance(marker, NotEq):
            v = marker.val
            filters.append(lambda x, v=v: x != v)

    strategy = st.floats(**kwargs)
    for f in filters:
        strategy = strategy.filter(f)
    return strategy


# ---------------------------------------------------------------------------
# from_counterexample
# ---------------------------------------------------------------------------


def from_counterexample(cert: ProofCertificate) -> dict[str, Any]:
    """Extract argument values from a counterexample certificate.

    Args:
        cert: A :class:`~provably.engine.ProofCertificate` with
            ``status == Status.COUNTEREXAMPLE``.

    Returns:
        The counterexample dict with the ``__return__`` key removed,
        containing only the input argument values.

    Raises:
        ValueError: If the certificate has no counterexample.

    Example::

        ce = from_counterexample(func.__proof__)
        # ce == {"x": -1, "y": 0}  (no __return__)
    """
    if cert.counterexample is None:
        raise ValueError(
            f"Certificate for '{cert.function_name}' has no counterexample "
            f"(status: {cert.status.value}). "
            "Pass a certificate with status COUNTEREXAMPLE."
        )
    return {k: v for k, v in cert.counterexample.items() if k != "__return__"}


# ---------------------------------------------------------------------------
# HypothesisResult + hypothesis_check
# ---------------------------------------------------------------------------


@dataclass
class HypothesisResult:
    """Result of a Hypothesis property test.

    Attributes:
        passed: ``True`` if no counterexample was found.
        counterexample: The falsifying example dict (input args only), or
            ``None`` if the test passed.
        examples_run: Number of examples Hypothesis executed.
    """

    passed: bool
    counterexample: dict[str, Any] | None
    examples_run: int


def hypothesis_check(
    func: Any,
    pre: Any = None,
    post: Any = None,
    max_examples: int = 1000,
) -> HypothesisResult:
    """Run Hypothesis property testing on a function.

    Uses type annotations to generate strategies via :func:`from_refinements`.
    Applies *pre* as an ``assume()`` filter and checks *post* on each example.

    Args:
        func: The function to test.
        pre: Optional precondition callable (same arity as *func*).
            Called with concrete argument values; ``assume(pre(*args))`` skips
            invalid inputs.
        post: Optional postcondition callable taking ``(*args, result)``.
            Must return truthy for the test to pass.
        max_examples: Maximum number of Hypothesis examples to run (default 1000).

    Returns:
        :class:`HypothesisResult` with ``passed``, ``counterexample``, and
        ``examples_run``.

    Raises:
        ImportError: If hypothesis is not installed.

    Example::

        result = hypothesis_check(
            my_func,
            pre=lambda x: x > 0,
            post=lambda x, r: r >= 0,
            max_examples=500,
        )
        assert result.passed
    """
    from hypothesis import HealthCheck, assume, given, settings
    from hypothesis import strategies as st

    # Resolve type hints for all parameters
    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}

    import inspect

    try:
        params = list(inspect.signature(func).parameters.keys())
    except (ValueError, TypeError):
        params = []

    # Build per-parameter strategies
    param_strategies: list[Any] = []
    for p in params:
        typ = hints.get(p, float)
        try:
            strategy = from_refinements(typ)
        except TypeError:
            # Unsupported type — fall back to floats
            strategy = st.floats(allow_nan=False, allow_infinity=False)
        param_strategies.append(strategy)

    # Mutable counter shared across closure
    counter: dict[str, int] = {"n": 0}
    found: dict[str, Any | None] = {"ce": None}

    # Build a combined tuple strategy so we can use a single named parameter
    # in _test (hypothesis does not support *args in @given functions).
    if len(param_strategies) == 0:
        # No parameters — run max_examples times with no args
        for _ in range(max_examples):
            counter["n"] += 1
            result_val = func()
            if post is not None and not post(result_val):
                found["ce"] = {}
                break
        ce = found["ce"]
        return HypothesisResult(
            passed=ce is None,
            counterexample=ce,
            examples_run=counter["n"],
        )

    tuple_strategy = st.tuples(*param_strategies)

    # suppress_health_check=list(HealthCheck) allows this to be called
    # from within a pytest test (suppresses nested_given, differing_executors).
    @settings(
        max_examples=max_examples,
        suppress_health_check=list(HealthCheck),
        deadline=None,
    )
    @given(args_tuple=tuple_strategy)
    def _test(args_tuple: tuple[Any, ...]) -> None:
        args = tuple(args_tuple)
        counter["n"] += 1
        if pre is not None:
            assume(pre(*args))
        result_val = func(*args)
        if post is not None and not post(*args, result_val):
            # Build counterexample dict
            ce = dict(zip(params, args, strict=False))
            found["ce"] = ce
            raise AssertionError(f"Postcondition failed: {ce} → {result_val}")

    try:
        _test()
    except Exception:
        pass

    ce = found["ce"]
    return HypothesisResult(
        passed=ce is None,
        counterexample=ce,
        examples_run=counter["n"],
    )


# ---------------------------------------------------------------------------
# proven_property decorator
# ---------------------------------------------------------------------------


def proven_property(
    func: Any = None,
    *,
    pre: Any = None,
    post: Any = None,
    max_examples: int = 1000,
) -> Any:
    """Decorator that verifies via Z3 first, falls back to Hypothesis if UNKNOWN.

    Attaches two attributes to the decorated function:

    - ``__proof__``: The :class:`~provably.engine.ProofCertificate` from Z3.
    - ``__hypothesis_result__``: A :class:`HypothesisResult` (``None`` if Z3
      succeeded or the status was not UNKNOWN).

    Args:
        func: The function (when used as bare ``@proven_property``).
        pre: Precondition — passed to both Z3 and Hypothesis.
        post: Postcondition — passed to both Z3 and Hypothesis.
        max_examples: Max Hypothesis examples (default 1000).

    Returns:
        The original function with ``__proof__`` and ``__hypothesis_result__``
        attached. No runtime overhead.

    Example::

        from provably.hypothesis import proven_property

        @proven_property(
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
        )
        def sqrt_approx(x: float) -> float:
            return x ** 0.5

        assert sqrt_approx.__proof__.status != Status.COUNTEREXAMPLE
    """
    import functools

    def decorator(fn: Any) -> Any:
        cert = verify_function(fn, pre=pre, post=post)

        hyp_result: HypothesisResult | None = None
        if cert.status == Status.UNKNOWN:
            hyp_result = hypothesis_check(fn, pre=pre, post=post, max_examples=max_examples)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper.__proof__ = cert  # type: ignore[attr-defined]
        wrapper.__hypothesis_result__ = hyp_result  # type: ignore[attr-defined]
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
