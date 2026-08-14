"""Targeted tests to cover edge paths in translator.py (new features)."""

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


class TestListCompClosureBound:
    def test_list_comp_with_closure_var(self) -> None:
        """range() bound from a closure int works."""
        # Simulate a closure var n = 3
        src = "def f(): return sum([i for i in range(n)])"
        expr = _translate(src, {}, closure_vars={"n": z3.IntVal(3)})
        assert z3.simplify(expr).as_long() == 3

    def test_list_comp_nonname_target_raises(self) -> None:
        """'for (a, b) in range(N)' tuple target raises."""
        # We need to hand-craft an AST with a Tuple target because Python parser
        # would reject a Tuple-target over a range of ints.
        node = ast.ListComp(
            elt=ast.Constant(value=0),
            generators=[
                ast.comprehension(
                    target=ast.Tuple(elts=[ast.Name("a", ast.Store()), ast.Name("b", ast.Store())], ctx=ast.Store()),
                    iter=ast.Call(
                        func=ast.Name("range", ast.Load()),
                        args=[ast.Constant(value=3)],
                        keywords=[],
                    ),
                    ifs=[],
                    is_async=0,
                )
            ],
        )
        ast.fix_missing_locations(node)
        t = Translator()
        with pytest.raises(TranslationError, match="simple name"):
            t._list_comp(node, {})

    def test_list_comp_range_zero_step_raises(self) -> None:
        """range(0, 5, 0) is invalid — step can't be zero."""
        src = "def f(): return [i for i in range(0, 5, 0)]"
        with pytest.raises(TranslationError, match="step cannot be zero"):
            _translate(src, {})

    def test_list_comp_range_four_args_raises(self) -> None:
        """range() with 4 args is invalid."""
        # Must craft via AST — Python parser would reject the call, but here we
        # parse the real function def and go through the translator.
        node = ast.ListComp(
            elt=ast.Constant(value=0),
            generators=[
                ast.comprehension(
                    target=ast.Name("i", ast.Store()),
                    iter=ast.Call(
                        func=ast.Name("range", ast.Load()),
                        args=[ast.Constant(value=0), ast.Constant(value=1),
                              ast.Constant(value=1), ast.Constant(value=1)],
                        keywords=[],
                    ),
                    ifs=[],
                    is_async=0,
                )
            ],
        )
        ast.fix_missing_locations(node)
        t = Translator()
        with pytest.raises(TranslationError, match="1-3 args"):
            t._list_comp(node, {})


class TestMapBuiltin:
    def test_map_min(self) -> None:
        """map(min, ...) fails — min needs 2 args but map gives 1 per call."""
        src = "def f(): return sum(map(min, [1, 2, 3]))"
        with pytest.raises(TypeError):  # _z3_min takes 2 args; TypeError at call time
            _translate(src, {})

    def test_map_lambda_zero_arity(self) -> None:
        """Lambda with zero args fails against 1-item input."""
        src = "def f(): return sum(map(lambda: 0, [1, 2, 3]))"
        with pytest.raises(TranslationError, match="arity mismatch"):
            _translate(src, {})


class TestFilterBuiltin:
    def test_filter_none_truthy_ints(self) -> None:
        """filter(None, [ints]) drops zeros."""
        src = "def f(): return sum(filter(None, [0, 5, 0, 10]))"
        expr = _translate(src, {})
        assert z3.simplify(expr).as_long() == 15


class TestBitwiseLShift:
    def test_lshift_zero(self) -> None:
        src = "def f(x): return x << 0"
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5, expr != 5)
        assert s.check() == z3.unsat


class TestEvalListLikeDirect:
    def test_scalar_via_in_raises(self) -> None:
        """'in' on a scalar right-side raises TranslationError."""
        src = "def f(x): return x in 42"
        x = z3.Int("x")
        with pytest.raises(TranslationError, match="list literal"):
            _translate(src, {"x": x})


class TestSumSortedComposition:
    def test_sum_of_map_of_sorted(self) -> None:
        """sum(map(lambda y: y+1, sorted([3,1,2])))."""
        src = "def f(): return sum(map(lambda y: y + 1, sorted([3, 1, 2])))"
        expr = _translate(src, {})
        # sorted = [1,2,3], map +1 = [2,3,4], sum = 9
        assert z3.simplify(expr).as_long() == 9


class TestInChainedRarePath:
    def test_chained_comparison_with_in_middle(self) -> None:
        """a < b < c form still works with basic ops."""
        src = "def f(x): return 0 < x < 10"
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5, z3.Not(expr))
        assert s.check() == z3.unsat
