"""Tests for provably.types — Z3 sort mapping and refinement type markers."""

from __future__ import annotations

from typing import Annotated

import pytest

from conftest import requires_z3

pytestmark = requires_z3

import z3

from provably.types import (
    python_type_to_z3_sort,
    make_z3_var,
    extract_refinements,
    Gt,
    Ge,
    Lt,
    Le,
    Between,
    NotEq,
)


# ---------------------------------------------------------------------------
# python_type_to_z3_sort
# ---------------------------------------------------------------------------


class TestPythonTypeToZ3Sort:
    def test_int_maps_to_int_sort(self) -> None:
        assert python_type_to_z3_sort(int) == z3.IntSort()

    def test_float_maps_to_real_sort(self) -> None:
        assert python_type_to_z3_sort(float) == z3.RealSort()

    def test_bool_maps_to_bool_sort(self) -> None:
        assert python_type_to_z3_sort(bool) == z3.BoolSort()

    def test_annotated_int_unwraps(self) -> None:
        typ = Annotated[int, Ge(0)]
        assert python_type_to_z3_sort(typ) == z3.IntSort()

    def test_annotated_float_unwraps(self) -> None:
        typ = Annotated[float, Le(1.0)]
        assert python_type_to_z3_sort(typ) == z3.RealSort()

    def test_annotated_bool_unwraps(self) -> None:
        typ = Annotated[bool, None]
        assert python_type_to_z3_sort(typ) == z3.BoolSort()

    def test_annotated_multiple_markers_unwraps(self) -> None:
        typ = Annotated[float, Ge(0), Le(1)]
        assert python_type_to_z3_sort(typ) == z3.RealSort()

    def test_unsupported_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="No Z3 sort"):
            python_type_to_z3_sort(str)  # type: ignore[arg-type]

    def test_unsupported_type_list_raises(self) -> None:
        with pytest.raises(TypeError, match="No Z3 sort"):
            python_type_to_z3_sort(list)  # type: ignore[arg-type]

    def test_unsupported_none_type_raises(self) -> None:
        with pytest.raises(TypeError):
            python_type_to_z3_sort(type(None))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# make_z3_var
# ---------------------------------------------------------------------------


class TestMakeZ3Var:
    def test_int_creates_int_var(self) -> None:
        v = make_z3_var("x", int)
        assert v.sort() == z3.IntSort()
        assert str(v) == "x"

    def test_float_creates_real_var(self) -> None:
        v = make_z3_var("y", float)
        assert v.sort() == z3.RealSort()
        assert str(v) == "y"

    def test_bool_creates_bool_var(self) -> None:
        v = make_z3_var("b", bool)
        assert v.sort() == z3.BoolSort()
        assert str(v) == "b"

    def test_annotated_float_creates_real_var(self) -> None:
        typ = Annotated[float, Ge(0), Le(1)]
        v = make_z3_var("t", typ)
        assert v.sort() == z3.RealSort()

    def test_annotated_int_creates_int_var(self) -> None:
        typ = Annotated[int, Between(1, 10)]
        v = make_z3_var("n", typ)
        assert v.sort() == z3.IntSort()

    def test_var_name_preserved(self) -> None:
        v = make_z3_var("my_var", float)
        assert "my_var" in str(v)


# ---------------------------------------------------------------------------
# extract_refinements
# ---------------------------------------------------------------------------


class TestExtractRefinements:
    def test_plain_type_returns_empty(self) -> None:
        x = z3.Real("x")
        constraints = extract_refinements(float, x)
        assert constraints == []

    def test_ge_produces_ge_constraint(self) -> None:
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, Ge(0)], x)
        assert len(constraints) == 1
        # Should be x >= 0
        s = z3.Solver()
        s.add(x == -1)
        s.add(constraints[0])
        assert s.check() == z3.unsat

    def test_gt_produces_gt_constraint(self) -> None:
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, Gt(0)], x)
        assert len(constraints) == 1
        # x > 0 should be unsatisfiable with x == 0
        s = z3.Solver()
        s.add(x == 0)
        s.add(constraints[0])
        assert s.check() == z3.unsat

    def test_le_produces_le_constraint(self) -> None:
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, Le(1)], x)
        assert len(constraints) == 1
        s = z3.Solver()
        s.add(x == 2)
        s.add(constraints[0])
        assert s.check() == z3.unsat

    def test_lt_produces_lt_constraint(self) -> None:
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, Lt(1)], x)
        assert len(constraints) == 1
        # x < 1 should be unsat for x == 1
        s = z3.Solver()
        s.add(x == 1)
        s.add(constraints[0])
        assert s.check() == z3.unsat

    def test_between_produces_two_constraints(self) -> None:
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, Between(0, 1)], x)
        assert len(constraints) == 2
        # x in [0, 1]
        s = z3.Solver()
        s.add(x == -0.5)
        s.add(*constraints)
        assert s.check() == z3.unsat

        s2 = z3.Solver()
        s2.add(x == 1.5)
        s2.add(*constraints)
        assert s2.check() == z3.unsat

        s3 = z3.Solver()
        s3.add(x == 0.5)
        s3.add(*constraints)
        assert s3.check() == z3.sat

    def test_noteq_produces_neq_constraint(self) -> None:
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, NotEq(0)], x)
        assert len(constraints) == 1
        # x != 0 unsat for x == 0
        s = z3.Solver()
        s.add(x == 0)
        s.add(constraints[0])
        assert s.check() == z3.unsat

    def test_multiple_markers_stacked(self) -> None:
        x = z3.Real("x")
        # 0 < x < 1 — two constraints
        typ = Annotated[float, Gt(0), Lt(1)]
        constraints = extract_refinements(typ, x)
        assert len(constraints) == 2

        s = z3.Solver()
        s.add(x == 0.5)
        s.add(z3.Not(z3.And(*constraints)))
        assert s.check() == z3.unsat  # 0.5 satisfies both

    def test_ge_and_le_together(self) -> None:
        x = z3.Real("x")
        typ = Annotated[float, Ge(0), Le(1)]
        constraints = extract_refinements(typ, x)
        assert len(constraints) == 2

    def test_callable_marker(self) -> None:
        """A callable marker is called with the variable and its result is used."""
        x = z3.Real("x")
        # callable marker: x must be even (x % 2 == 0 — not really useful for reals,
        # but test the callable path)
        marker = lambda v: v >= 10  # noqa: E731
        constraints = extract_refinements(Annotated[float, marker], x)
        assert len(constraints) == 1
        # x >= 10 unsat for x == 5
        s = z3.Solver()
        s.add(x == 5)
        s.add(constraints[0])
        assert s.check() == z3.unsat

    def test_int_variable(self) -> None:
        n = z3.Int("n")
        constraints = extract_refinements(Annotated[int, Ge(1), Le(100)], n)
        assert len(constraints) == 2
        assert constraints[0].sort() == z3.BoolSort()

    def test_between_integer_bounds(self) -> None:
        n = z3.Int("n")
        constraints = extract_refinements(Annotated[int, Between(1, 10)], n)
        assert len(constraints) == 2
        s = z3.Solver()
        s.add(n == 0)
        s.add(*constraints)
        assert s.check() == z3.unsat


# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------


class TestConvenienceAliases:
    """Test that Positive, NonNegative, UnitInterval exist (if defined).

    If the library does not export them yet, these tests are marked xfail
    rather than erroring — they document the intended API.
    """

    def test_positive_alias_exists_or_xfail(self) -> None:
        try:
            from provably.types import Positive  # type: ignore[attr-defined]
        except ImportError:
            pytest.xfail("Positive alias not yet exported from provably.types")

        x = z3.Real("x")
        # Positive is Annotated[float, Gt(0)] — use it directly as the type
        constraints = extract_refinements(Positive, x)
        assert len(constraints) >= 1

    def test_nonnegative_alias_exists_or_xfail(self) -> None:
        try:
            from provably.types import NonNegative  # type: ignore[attr-defined]
        except ImportError:
            pytest.xfail("NonNegative alias not yet exported from provably.types")

        x = z3.Real("x")
        # NonNegative is Annotated[float, Ge(0)] — use it directly
        constraints = extract_refinements(NonNegative, x)
        assert len(constraints) >= 1

    def test_unit_interval_alias_exists_or_xfail(self) -> None:
        try:
            from provably.types import UnitInterval  # type: ignore[attr-defined]
        except ImportError:
            pytest.xfail("UnitInterval alias not yet exported from provably.types")

        x = z3.Real("x")
        # UnitInterval is Annotated[float, Between(0, 1)] — use it directly
        constraints = extract_refinements(UnitInterval, x)
        assert len(constraints) >= 2  # x >= 0 and x <= 1


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestRepr:
    def test_gt_repr(self) -> None:
        assert repr(Gt(5)) == "Gt(5)"

    def test_ge_repr(self) -> None:
        assert repr(Ge(0)) == "Ge(0)"

    def test_lt_repr(self) -> None:
        assert repr(Lt(10)) == "Lt(10)"

    def test_le_repr(self) -> None:
        assert repr(Le(1.5)) == "Le(1.5)"

    def test_between_repr(self) -> None:
        assert repr(Between(0, 1)) == "Between(0, 1)"

    def test_noteq_repr(self) -> None:
        assert repr(NotEq(0)) == "NotEq(0)"
