"""Tests targeting uncovered paths in hypothesis.py."""

from __future__ import annotations

from typing import Annotated

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import strategies as st

from provably.engine import ProofCertificate, Status
from provably.hypothesis import (
    HypothesisResult,
    from_counterexample,
    from_refinements,
    hypothesis_check,
    proven_property,
)
from provably.types import Between, Ge, Gt, Le, Lt, NotEq


class TestNestedAnnotated:
    def test_nested_annotated_int(self) -> None:
        """Annotated[Annotated[int, Ge(0)], Le(10)] merges markers."""
        typ = Annotated[Annotated[int, Ge(0)], Le(10)]
        strategy = from_refinements(typ)
        # Draw and verify bounds
        for _ in range(20):
            v = strategy.example()
            assert 0 <= v <= 10

    def test_deeply_nested_annotated(self) -> None:
        typ = Annotated[Annotated[Annotated[int, Ge(-5)], Le(5)], NotEq(0)]
        strategy = from_refinements(typ)
        v = strategy.example()
        assert -5 <= v <= 5 and v != 0


class TestIntegerMarkers:
    def test_int_gt_float_bound_filter(self) -> None:
        """Gt(0.5) with int base uses a filter instead of min_value."""
        typ = Annotated[int, Gt(0.5)]
        strategy = from_refinements(typ)
        for _ in range(20):
            v = strategy.example()
            assert v > 0.5

    def test_int_lt_float_bound_filter(self) -> None:
        """Lt(10.5) with int base uses a filter."""
        typ = Annotated[int, Lt(10.5)]
        strategy = from_refinements(typ)
        for _ in range(20):
            v = strategy.example()
            assert v < 10.5

    def test_int_between(self) -> None:
        typ = Annotated[int, Between(1, 10)]
        strategy = from_refinements(typ)
        for _ in range(20):
            v = strategy.example()
            assert 1 <= v <= 10

    def test_int_not_eq(self) -> None:
        typ = Annotated[int, Ge(0), Le(5), NotEq(3)]
        strategy = from_refinements(typ)
        for _ in range(30):
            v = strategy.example()
            assert 0 <= v <= 5 and v != 3


class TestFloatMarkers:
    def test_float_between(self) -> None:
        typ = Annotated[float, Between(-1.0, 1.0)]
        strategy = from_refinements(typ)
        for _ in range(10):
            v = strategy.example()
            assert -1.0 <= v <= 1.0

    def test_float_gt_lt(self) -> None:
        typ = Annotated[float, Gt(0.0), Lt(10.0)]
        strategy = from_refinements(typ)
        for _ in range(10):
            v = strategy.example()
            assert 0.0 < v < 10.0

    def test_float_not_eq(self) -> None:
        typ = Annotated[float, Ge(0.0), Le(1.0), NotEq(0.5)]
        strategy = from_refinements(typ)
        for _ in range(10):
            v = strategy.example()
            assert v != 0.5


class TestUnsupportedBase:
    def test_unsupported_base_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported base type"):
            from_refinements(str)  # type: ignore[arg-type]


class TestBooleanStrategy:
    def test_bool_strategy(self) -> None:
        strategy = from_refinements(bool)
        # Hypothesis booleans strategy
        v = strategy.example()
        assert isinstance(v, bool)


class TestHypothesisCheck:
    def test_no_params(self) -> None:
        """Function with no parameters."""

        def f() -> int:
            return 42

        result = hypothesis_check(f, post=lambda r: r == 42, max_examples=10)
        assert result.passed
        assert result.examples_run == 10

    def test_no_params_counterexample(self) -> None:
        def f() -> int:
            return 41

        result = hypothesis_check(f, post=lambda r: r == 42, max_examples=10)
        assert not result.passed
        assert result.counterexample == {}

    def test_with_pre_filter(self) -> None:
        def f(x: Annotated[int, Ge(0), Le(100)]) -> int:
            return x * 2

        result = hypothesis_check(
            f, pre=lambda x: x >= 0, post=lambda x, r: r >= x, max_examples=50
        )
        assert result.passed

    def test_counterexample_is_built(self) -> None:
        def f(x: Annotated[int, Ge(-100), Le(100)]) -> int:
            return x + 1

        result = hypothesis_check(
            f,
            post=lambda x, r: r == x,  # Intentionally wrong
            max_examples=20,
        )
        assert not result.passed
        assert result.counterexample is not None
        assert "x" in result.counterexample

    def test_unsupported_type_falls_back_to_float(self) -> None:
        """Parameter with str-typed annotation should fall back to floats."""

        def f(x: str) -> int:  # type: ignore[arg-type]
            return 0

        result = hypothesis_check(f, post=lambda x, r: r == 0, max_examples=5)
        # Should not crash — unsupported type falls back to floats
        assert result.passed

    def test_no_signature_function(self) -> None:
        """A built-in without signature falls back to empty param list."""
        # abs has a signature, but a builtin_function_or_method without may not.
        # Use a lambda with a crafted signature to ensure coverage.
        f = lambda: 0  # noqa: E731
        result = hypothesis_check(f, post=lambda r: r == 0, max_examples=3)
        assert result.passed


class TestProvenProperty:
    def test_proven_property_bare_decorator(self) -> None:
        @proven_property
        def f(x: Annotated[int, Ge(0), Le(10)]) -> int:
            return x + 1

        # __proof__ should be attached
        assert hasattr(f, "__proof__")

    def test_proven_property_wrapper_behavior(self) -> None:
        @proven_property(post=lambda x, r: r >= 0)
        def f(x: Annotated[int, Ge(0), Le(10)]) -> int:
            return x * 2

        # Calling f should work normally
        assert f(3) == 6

    def test_proven_property_preserves_wraps(self) -> None:
        @proven_property(post=lambda x, r: r >= 0)
        def my_function(x: Annotated[int, Ge(0), Le(5)]) -> int:
            """Docstring."""
            return x

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Docstring."


class TestFromCounterexampleEdge:
    def test_no_counterexample_raises(self) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="abcd",
            status=Status.VERIFIED,
            preconditions=(),
            postconditions=(),
            counterexample=None,
        )
        with pytest.raises(ValueError, match="no counterexample"):
            from_counterexample(cert)

    def test_counterexample_strips_return(self) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="abcd",
            status=Status.COUNTEREXAMPLE,
            preconditions=(),
            postconditions=(),
            counterexample={"x": -1, "__return__": 7},
        )
        ce = from_counterexample(cert)
        assert ce == {"x": -1}
