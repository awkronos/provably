"""Targeted coverage: generator expressions with range(a,b)/(a,b,c), tuple subscripts."""

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


class TestSumGeneratorRangeVariants:
    def test_sum_gen_range_two_args(self) -> None:
        src = "def f(): return sum(i for i in range(2, 5))"
        expr = _translate(src, {})
        # 2+3+4 = 9
        assert z3.simplify(expr).as_long() == 9

    def test_sum_gen_range_three_args(self) -> None:
        src = "def f(): return sum(i for i in range(0, 10, 2))"
        expr = _translate(src, {})
        # 0+2+4+6+8 = 20
        assert z3.simplify(expr).as_long() == 20

    def test_sum_gen_range_empty(self) -> None:
        src = "def f(): return sum(i for i in range(5, 5))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0

    def test_sum_gen_range_overflow_raises(self) -> None:
        src = "def f(): return sum(i for i in range(500))"
        with pytest.raises(TranslationError, match="unroll"):
            _translate(src, {})


class TestTupleSubscript:
    def test_tuple_subscript_out_of_range_raises(self) -> None:
        src = "def f(): return (10, 20)[5]"
        with pytest.raises(TranslationError, match="out of range"):
            _translate(src, {})

    def test_tuple_empty_produces_zero(self) -> None:
        # zero-arg tuple: translator returns IntVal(0)
        src = "def f(): return ()"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0


class TestCoerceBool:
    def test_bool_plus_int_left(self) -> None:
        """(x > 0) + 1 — bool on left, int on right."""
        x = z3.Int("x")
        src = "def f(x): return (x > 0) + 1"
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5, expr != 2)  # True + 1 = 2
        assert s.check() == z3.unsat

    def test_int_plus_bool_right(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return 1 + (x > 0)"
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5, expr != 2)
        assert s.check() == z3.unsat
