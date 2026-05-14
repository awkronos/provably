"""Tests for sorted / map / filter builtins on list literals."""

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


# ---------------------------------------------------------------------------
# sorted()
# ---------------------------------------------------------------------------


class TestSorted:
    def test_sorted_literal_sum(self) -> None:
        src = "def f(): return sum(sorted([3, 1, 2]))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 6

    def test_sorted_literal_first(self) -> None:
        # sorted([3, 1, 2]) => [1, 2, 3]; use 'in' to check membership
        src = "def f(): return 1 in sorted([3, 1, 2])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_sorted_from_comprehension(self) -> None:
        src = "def f(): return sum(sorted([4 - i for i in range(4)]))"
        expr = _translate(src, {})
        # [4,3,2,1] sorted = [1,2,3,4] sum = 10
        assert z3.simplify(expr).as_long() == 10

    def test_sorted_real_values(self) -> None:
        src = "def f(): return sum(sorted([0.5, 0.25, 0.75]))"
        expr = _translate(src, {})
        # 0.5 + 0.25 + 0.75 = 1.5
        s = z3.Solver()
        s.add(expr != z3.RealVal("1.5"))
        assert s.check() == z3.unsat

    def test_sorted_symbolic_raises(self) -> None:
        x = z3.Int("x")
        src = "def f(x): return sum(sorted([x, 1, 2]))"
        with pytest.raises(TranslationError, match="symbolic"):
            _translate(src, {"x": x})

    def test_sorted_arity_raises(self) -> None:
        src = "def f(): return sorted([1, 2], [3, 4])"
        with pytest.raises(TranslationError, match="takes exactly 1 argument"):
            _translate(src, {})


# ---------------------------------------------------------------------------
# map()
# ---------------------------------------------------------------------------


class TestMap:
    def test_map_lambda_doubles(self) -> None:
        src = "def f(): return sum(map(lambda x: x * 2, [1, 2, 3]))"
        expr = _translate(src, {})
        # 2+4+6 = 12
        assert z3.simplify(expr).as_long() == 12

    def test_map_abs(self) -> None:
        src = "def f(): return sum(map(abs, [-1, 2, -3]))"
        expr = _translate(src, {})
        # 1+2+3 = 6
        assert z3.simplify(expr).as_long() == 6

    def test_map_over_comprehension(self) -> None:
        src = "def f(): return sum(map(lambda x: x + 1, [i for i in range(3)]))"
        expr = _translate(src, {})
        # [0,1,2] -> [1,2,3] sum = 6
        assert z3.simplify(expr).as_long() == 6

    def test_map_arity_raises(self) -> None:
        src = "def f(): return map(abs)"
        with pytest.raises(TranslationError, match="takes exactly 2 arguments"):
            _translate(src, {})

    def test_map_bad_func_raises(self) -> None:
        src = "def f(): return sum(map(foo, [1, 2, 3]))"
        with pytest.raises(TranslationError):
            _translate(src, {})

    def test_map_lambda_arity_mismatch_raises(self) -> None:
        # Lambda takes 2 args but map provides 1 per invocation
        src = "def f(): return sum(map(lambda x, y: x + y, [1, 2, 3]))"
        with pytest.raises(TranslationError, match="arity mismatch"):
            _translate(src, {})

    def test_map_non_callable_raises(self) -> None:
        src = "def f(): return sum(map(42, [1, 2, 3]))"
        with pytest.raises(TranslationError, match="lambda or simple name"):
            _translate(src, {})


# ---------------------------------------------------------------------------
# filter()
# ---------------------------------------------------------------------------


class TestFilter:
    def test_filter_odd(self) -> None:
        src = "def f(): return sum(filter(lambda x: x % 2 != 0, [1, 2, 3, 4, 5]))"
        expr = _translate(src, {})
        # [1, 3, 5] sum = 9
        assert z3.simplify(expr).as_long() == 9

    def test_filter_positive(self) -> None:
        src = "def f(): return sum(filter(lambda x: x > 0, [-1, 2, -3, 4]))"
        expr = _translate(src, {})
        # [2, 4] sum = 6
        assert z3.simplify(expr).as_long() == 6

    def test_filter_none(self) -> None:
        src = "def f(): return sum(filter(None, [0, 1, 0, 2, 0, 3]))"
        expr = _translate(src, {})
        # [1, 2, 3] sum = 6
        assert z3.simplify(expr).as_long() == 6

    def test_filter_empty_result(self) -> None:
        src = "def f(): return sum(filter(lambda x: x > 10, [1, 2, 3]))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0

    def test_filter_arity_raises(self) -> None:
        src = "def f(): return filter(abs)"
        with pytest.raises(TranslationError, match="takes exactly 2 arguments"):
            _translate(src, {})

    def test_filter_symbolic_predicate_raises(self) -> None:
        x = z3.Int("x")
        # Symbolic predicate can't decide a concrete bool for each input
        src = "def f(x): return sum(filter(lambda y: y > x, [1, 2, 3]))"
        with pytest.raises(TranslationError, match="concrete bool"):
            _translate(src, {"x": x})


class TestBuiltinsInVerified:
    def test_map_verified(self) -> None:
        from provably import verified

        @verified(post=lambda result: result == 12)
        def sum_of_doubles() -> int:
            return sum(map(lambda x: x * 2, [1, 2, 3]))  # noqa: C417

        assert sum_of_doubles.__proof__.verified  # type: ignore[attr-defined]

    def test_filter_verified(self) -> None:
        from provably import verified

        @verified(post=lambda result: result == 9)
        def sum_of_odds() -> int:
            return sum(filter(lambda x: x % 2 != 0, [1, 2, 3, 4, 5]))

        assert sum_of_odds.__proof__.verified  # type: ignore[attr-defined]

    def test_sorted_verified(self) -> None:
        from provably import verified

        @verified(post=lambda result: result == 6)
        def sorted_sum() -> int:
            return sum(sorted([3, 1, 2]))

        assert sorted_sum.__proof__.verified  # type: ignore[attr-defined]
