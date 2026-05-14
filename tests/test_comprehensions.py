"""Tests for list comprehensions + list literals consumed by builtins."""

from __future__ import annotations

import ast
import textwrap

import pytest
import z3

from provably.translator import TranslationError, Translator


def _parse_func(source: str) -> ast.FunctionDef:
    return ast.parse(textwrap.dedent(source)).body[0]  # type: ignore[return-value]


def _translate(
    source: str,
    param_vars: dict[str, z3.ExprRef],
    closure_vars: dict[str, z3.ExprRef] | None = None,
) -> z3.ExprRef | None:
    func_ast = _parse_func(source)
    t = Translator(closure_vars=closure_vars or {})
    return t.translate(func_ast, param_vars).return_expr


# ---------------------------------------------------------------------------
# sum / any / all over list comprehensions
# ---------------------------------------------------------------------------


class TestListCompSum:
    def test_list_comp_sum_range(self) -> None:
        src = "def f(): return sum([i*2 for i in range(3)])"
        expr = _translate(src, {})
        # 0 + 2 + 4 = 6
        assert z3.is_int_value(z3.simplify(expr))
        assert z3.simplify(expr).as_long() == 6

    def test_list_comp_sum_with_params(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return sum([x + i for i in range(3)])"
        expr = _translate(src, {"x": x})
        # (x+0) + (x+1) + (x+2) = 3x + 3
        s = z3.Solver()
        s.add(expr != 3 * x + 3)
        assert s.check() == z3.unsat

    def test_list_comp_direct_literal_use(self) -> None:
        src = "def f(): return sum([x for x in range(4)])"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 6

    def test_list_comp_sum_range_two_args(self) -> None:
        src = "def f(): return sum([i for i in range(2, 5)])"
        expr = _translate(src, {})
        # 2 + 3 + 4 = 9
        assert z3.simplify(expr).as_long() == 9

    def test_list_comp_sum_range_three_args(self) -> None:
        src = "def f(): return sum([i for i in range(0, 10, 2)])"
        expr = _translate(src, {})
        # 0+2+4+6+8 = 20
        assert z3.simplify(expr).as_long() == 20

    def test_list_comp_empty(self) -> None:
        src = "def f(): return sum([i for i in range(0)])"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0


class TestListCompAnyAll:
    def test_list_comp_any(self) -> None:
        src = "def f(): return any([i > 2 for i in range(4)])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_list_comp_any_false(self) -> None:
        src = "def f(): return any([i > 100 for i in range(4)])"
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_list_comp_all_true(self) -> None:
        src = "def f(): return all([i >= 0 for i in range(3)])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_list_comp_all_false(self) -> None:
        src = "def f(): return all([i > 0 for i in range(3)])"
        expr = _translate(src, {})
        # i=0 => 0 > 0 is false
        assert z3.is_false(z3.simplify(expr))

    def test_empty_any_is_false(self) -> None:
        src = "def f(): return any([i > 0 for i in range(0)])"
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_empty_all_is_true(self) -> None:
        src = "def f(): return all([i > 0 for i in range(0)])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))


# ---------------------------------------------------------------------------
# Restrictions
# ---------------------------------------------------------------------------


class TestListCompRestrictions:
    def test_multiple_generators_raises(self) -> None:
        src = "def f(): return sum([i + j for i in range(2) for j in range(2)])"
        with pytest.raises(TranslationError, match="multiple generators"):
            _translate(src, {})

    def test_with_if_raises(self) -> None:
        src = "def f(): return sum([i for i in range(5) if i > 2])"
        with pytest.raises(TranslationError, match="Filtered"):
            _translate(src, {})

    def test_non_range_iter_raises(self) -> None:
        src = "def f(): return sum([i for i in [1, 2, 3]])"
        with pytest.raises(TranslationError, match="range"):
            _translate(src, {})

    def test_overflow_raises(self) -> None:
        src = "def f(): return sum([i for i in range(500)])"
        with pytest.raises(TranslationError, match="unroll"):
            _translate(src, {})

    def test_symbolic_range_raises(self) -> None:
        n = z3.Int("n")
        src = "def f(n): return sum([i for i in range(n)])"
        with pytest.raises(TranslationError, match="constant integer"):
            _translate(src, {"n": n})


# ---------------------------------------------------------------------------
# any / all on direct list literals still works
# ---------------------------------------------------------------------------


class TestListLiteralAnyAll:
    def test_any_list_literal(self) -> None:
        src = "def f(): return any([False, True, False])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_all_list_literal(self) -> None:
        src = "def f(): return all([True, True, True])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_any_empty_list(self) -> None:
        src = "def f(): return any([])"
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_all_empty_list(self) -> None:
        src = "def f(): return all([])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))
