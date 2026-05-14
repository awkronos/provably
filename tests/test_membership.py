"""Tests for 'in' and 'not in' operators over list literals."""

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
) -> z3.ExprRef | None:
    func_ast = _parse_func(source)
    t = Translator()
    return t.translate(func_ast, param_vars).return_expr


class TestInListLiteral:
    def test_in_literal_true(self) -> None:
        src = "def f(): return 2 in [1, 2, 3]"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_in_literal_false(self) -> None:
        src = "def f(): return 5 in [1, 2, 3]"
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_not_in_literal_true(self) -> None:
        src = "def f(): return 5 not in [1, 2, 3]"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_not_in_literal_false(self) -> None:
        src = "def f(): return 2 not in [1, 2, 3]"
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_in_with_param(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return x in [1, 2, 3]"
        expr = _translate(src, {"x": x})
        # x=2 => True
        s = z3.Solver()
        s.add(x == 2)
        s.add(z3.Not(expr))
        assert s.check() == z3.unsat
        # x=5 => False
        s2 = z3.Solver()
        s2.add(x == 5)
        s2.add(expr)
        assert s2.check() == z3.unsat

    def test_in_empty_list_is_false(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return x in []"
        expr = _translate(src, {"x": x})
        assert z3.is_false(z3.simplify(expr))

    def test_not_in_empty_list_is_true(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return x not in []"
        expr = _translate(src, {"x": x})
        assert z3.is_true(z3.simplify(expr))

    def test_in_singleton(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return x in [42]"
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 42)
        s.add(z3.Not(expr))
        assert s.check() == z3.unsat

    def test_in_list_comp(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return x in [i for i in range(3)]"
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 1)
        s.add(z3.Not(expr))
        assert s.check() == z3.unsat


class TestInRaises:
    def test_in_non_list_raises(self) -> None:
        src = "def f(x): return x in 5"
        x = z3.Int("x")
        with pytest.raises(TranslationError, match="list literal or comprehension"):
            _translate(src, {"x": x})


class TestInVerified:
    def test_is_small_verified(self) -> None:
        from provably import verified

        @verified(pre=lambda x: (x >= 1) & (x <= 3), post=lambda x, result: result)
        def is_small(x: int) -> bool:
            return x in [1, 2, 3]

        assert is_small.__proof__.verified  # type: ignore[attr-defined]

    def test_not_in_verified(self) -> None:
        from provably import verified

        @verified(
            pre=lambda x: (x >= 5) & (x <= 10),
            post=lambda x, result: result,
        )
        def not_small(x: int) -> bool:
            return x not in [1, 2, 3]

        assert not_small.__proof__.verified  # type: ignore[attr-defined]
