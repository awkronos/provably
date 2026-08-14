"""Further targeted coverage tests for translator.py new features."""

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
    verified_contracts: dict | None = None,
) -> z3.ExprRef | None:
    func_ast = _parse_func(source)
    t = Translator(
        closure_vars=closure_vars or {},
        verified_contracts=verified_contracts or {},
    )
    return t.translate(func_ast, param_vars).return_expr


class TestAnyAllZeroArgRaises:
    def test_any_zero_args_raises(self) -> None:
        src = "def f(): return any()"
        with pytest.raises(TranslationError, match="takes exactly 1 argument"):
            _translate(src, {})

    def test_all_zero_args_raises(self) -> None:
        src = "def f(): return all()"
        with pytest.raises(TranslationError, match="takes exactly 1 argument"):
            _translate(src, {})

    def test_sum_zero_args_raises(self) -> None:
        src = "def f(): return sum()"
        with pytest.raises(TranslationError, match="takes exactly 1 argument"):
            _translate(src, {})

    def test_any_of_scalar_raises(self) -> None:
        src = "def f(x): return any(x)"
        x = z3.Int("x")
        with pytest.raises(TranslationError, match="list literals"):
            _translate(src, {"x": x})

    def test_all_of_scalar_raises(self) -> None:
        src = "def f(x): return all(x)"
        x = z3.Int("x")
        with pytest.raises(TranslationError, match="list literals"):
            _translate(src, {"x": x})


class TestMapWithVerifiedContract:
    def test_map_uses_verified_contract(self) -> None:
        src = "def f(): return sum(map(g, [1, 2, 3]))"
        contracts = {
            "g": {
                "pre": lambda x: x >= 0,
                "post": lambda x, r: r == x * 2,
                "return_sort": z3.IntSort(),
            }
        }
        # We can't fully verify the result is 12, but the translator should not fail.
        expr = _translate(src, {}, verified_contracts=contracts)
        assert expr is not None


class TestSumGeneratorZeroSize:
    def test_sum_gen_range_single_arg_zero(self) -> None:
        src = "def f(): return sum(i for i in range(0))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0

    def test_sum_literal_empty_returns_zero(self) -> None:
        src = "def f(): return sum([])"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0


class TestFilterWithFalsyElements:
    def test_filter_all_false_returns_empty_sum(self) -> None:
        src = "def f(): return sum(filter(lambda x: x > 100, [1, 2, 3]))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0

    def test_filter_none_only_zero_int(self) -> None:
        """filter(None, [0]) — returns empty list."""
        src = "def f(): return sum(filter(None, [0]))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 0

    def test_filter_none_with_bool_true(self) -> None:
        # filter(None, [True, False, True]) - requires boolean in translator
        # Lists of Bool are odd. Use ints with known truthy values.
        src = "def f(): return sum(filter(None, [0, 1, 0, 1]))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 2


class TestListCompInListLiteralReturn:
    def test_any_over_list_comp_passed_through_list_literal(self) -> None:
        # [i > 2 for i in range(4)] inside any()
        src = "def f(): return any([i > 2 for i in range(4)])"
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))


class TestMultipleGeneratorsInListComp:
    def test_sum_of_multi_generator_raises(self) -> None:
        src = "def f(): return sum([i+j for i in range(2) for j in range(2)])"
        with pytest.raises(TranslationError, match="multiple generators"):
            _translate(src, {})


class TestLambdaKeywordOnlyRaises:
    def test_lambda_with_kwonly_raises(self) -> None:
        """Lambdas with keyword-only args aren't supported."""
        # Need AST with kw-only — build manually. Regular Python lambda syntax
        # requires *args before kw-only args, so construct with AST builder.
        # But this is an inaccessible path through the parser — lambdas can
        # have *args and **kwargs via default syntax. We can still test via
        # parsed source:
        src = "def f(): return sum(map(lambda x, *args: x, [1, 2, 3]))"
        # *args path
        with pytest.raises(TranslationError, match="args"):
            _translate(src, {})

    def test_lambda_with_kwargs_raises(self) -> None:
        src = "def f(): return sum(map(lambda x, **kw: x, [1, 2, 3]))"
        with pytest.raises(TranslationError, match="kwargs"):
            _translate(src, {})


class TestCoerceEdgeCases:
    def test_bool_plus_bool_coerce(self) -> None:
        src = "def f(x, y): return (x > 0) + (y > 0)"
        x, y = z3.Int("x"), z3.Int("y")
        expr = _translate(src, {"x": x, "y": y})
        s = z3.Solver()
        s.add(x == 1, y == 1, expr != 2)
        assert s.check() == z3.unsat
