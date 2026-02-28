"""Tests for the Python AST → Z3 translator (the TCB).

The translator is the Trusted Computing Base — bugs here can produce
unsound proofs. These tests form the soundness regression suite.
"""

from __future__ import annotations

import ast
import textwrap

import pytest

from conftest import requires_z3

pytestmark = requires_z3

import z3

from provably.translator import Translator, TranslationError


def _parse_func(source: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    return tree.body[0]  # type: ignore[return-value]


def _translate(source: str, param_vars: dict[str, z3.ExprRef]) -> z3.ExprRef:
    """Helper: translate source and return the return expression."""
    func_ast = _parse_func(source)
    t = Translator()
    result = t.translate(func_ast, param_vars)
    assert result.return_expr is not None, f"No return expression: {result.warnings}"
    return result.return_expr


# ---------------------------------------------------------------------------
# Expression translation
# ---------------------------------------------------------------------------


class TestExpressions:
    def test_constant_int(self) -> None:
        src = """
def f():
    return 42
"""
        expr = _translate(src, {})
        assert z3.is_int_value(expr)
        assert expr.as_long() == 42

    def test_constant_float(self) -> None:
        src = """
def f():
    return 3.14
"""
        expr = _translate(src, {})
        assert z3.is_rational_value(expr)
        assert abs(float(expr.as_fraction()) - 3.14) < 1e-10

    def test_constant_bool(self) -> None:
        src = """
def f():
    return True
"""
        expr = _translate(src, {})
        assert z3.is_true(expr)

    def test_variable_reference(self) -> None:
        src = """
def f(x):
    return x
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        assert expr is x

    def test_arithmetic_add(self) -> None:
        src = """
def f(x, y):
    return x + y
"""
        x, y = z3.Real("x"), z3.Real("y")
        expr = _translate(src, {"x": x, "y": y})
        s = z3.Solver()
        s.add(x == 3, y == 4)
        s.add(expr != 7)
        assert s.check() == z3.unsat

    def test_arithmetic_sub_mul_div(self) -> None:
        src = """
def f(x):
    return (x * 2 - 1) / 3
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr != 3)
        assert s.check() == z3.unsat

    def test_unary_neg(self) -> None:
        src = """
def f(x):
    return -x
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 7)
        s.add(expr != -7)
        assert s.check() == z3.unsat

    def test_power_square(self) -> None:
        src = """
def f(x):
    return x ** 2
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr != 25)
        assert s.check() == z3.unsat

    def test_boolean_and_or(self) -> None:
        src = """
def f(x, y):
    return x > 0 and y > 0
"""
        x, y = z3.Real("x"), z3.Real("y")
        expr = _translate(src, {"x": x, "y": y})
        s = z3.Solver()
        s.add(x == 1, y == -1)
        s.add(expr)
        assert s.check() == z3.unsat  # (1 > 0) and (-1 > 0) is false

    def test_chained_comparison(self) -> None:
        src = """
def f(x):
    return 0 < x < 10
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(z3.Not(expr))
        assert s.check() == z3.unsat  # 0 < 5 < 10 is True

    def test_chained_comparison_four_operands(self) -> None:
        """a < b < c < d should translate to And(a<b, b<c, c<d)."""
        src = """
def f(a, b, c, d):
    return a < b < c < d
"""
        a, b, c, d = z3.Real("a"), z3.Real("b"), z3.Real("c"), z3.Real("d")
        expr = _translate(src, {"a": a, "b": b, "c": c, "d": d})
        s = z3.Solver()
        # All strictly increasing: should be sat
        s.add(a == 1, b == 2, c == 3, d == 4)
        s.add(z3.Not(expr))
        assert s.check() == z3.unsat  # 1 < 2 < 3 < 4 is True

        # Violates second comparison
        s2 = z3.Solver()
        s2.add(a == 1, b == 2, c == 2, d == 4)
        s2.add(expr)
        assert s2.check() == z3.unsat  # 1 < 2 < 2 < 4 is False (2 < 2 fails)

    def test_if_expression(self) -> None:
        src = """
def f(x):
    return x if x > 0 else -x
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        # Should behave like abs(x)
        s = z3.Solver()
        s.add(x == -3)
        s.add(expr != 3)
        assert s.check() == z3.unsat

    def test_builtin_min(self) -> None:
        src = """
def f(x, y):
    return min(x, y)
"""
        x, y = z3.Real("x"), z3.Real("y")
        expr = _translate(src, {"x": x, "y": y})
        s = z3.Solver()
        s.add(x == 3, y == 7)
        s.add(expr != 3)
        assert s.check() == z3.unsat

    def test_builtin_max(self) -> None:
        src = """
def f(x, y):
    return max(x, y)
"""
        x, y = z3.Real("x"), z3.Real("y")
        expr = _translate(src, {"x": x, "y": y})
        s = z3.Solver()
        s.add(x == 3, y == 7)
        s.add(expr != 7)
        assert s.check() == z3.unsat

    def test_builtin_abs(self) -> None:
        src = """
def f(x):
    return abs(x)
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == -5)
        s.add(expr != 5)
        assert s.check() == z3.unsat


# ---------------------------------------------------------------------------
# Statement translation
# ---------------------------------------------------------------------------


class TestStatements:
    def test_simple_assignment(self) -> None:
        src = """
def f(x):
    y = x + 1
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 10)
        s.add(expr != 11)
        assert s.check() == z3.unsat

    def test_multiple_assignments(self) -> None:
        src = """
def f(x):
    y = x * 2
    z = y + 1
    return z
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 3)
        s.add(expr != 7)
        assert s.check() == z3.unsat

    def test_augmented_assign_add(self) -> None:
        src = """
def f(x):
    y = x
    y += 5
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 10)
        s.add(expr != 15)
        assert s.check() == z3.unsat

    def test_augmented_assign_sub(self) -> None:
        src = """
def f(x):
    y = x
    y -= 3
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 10)
        s.add(expr != 7)
        assert s.check() == z3.unsat

    def test_augmented_assign_mul(self) -> None:
        src = """
def f(x):
    y = x
    y *= 4
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 3)
        s.add(expr != 12)
        assert s.check() == z3.unsat

    def test_augmented_assign_div(self) -> None:
        src = """
def f(x):
    y = x
    y /= 2
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 10)
        s.add(expr != 5)
        assert s.check() == z3.unsat

    def test_reassignment(self) -> None:
        src = """
def f(x):
    y = x
    y = y * 2
    y = y + 1
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr != 11)
        assert s.check() == z3.unsat

    def test_assert_becomes_constraint(self) -> None:
        src = """
def f(x):
    assert x > 0
    return x
"""
        x = z3.Real("x")
        func_ast = _parse_func(src)
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert len(result.constraints) == 1

    def test_docstring_expression_skipped(self) -> None:
        """String constants in Expr statements (docstrings) should be skipped."""
        src = """
def f(x):
    \"\"\"This is a docstring.\"\"\"
    return x + 1
"""
        x = z3.Real("x")
        # Should not raise TranslationError
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr != 6)
        assert s.check() == z3.unsat


# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------


class TestControlFlow:
    def test_if_else_return(self) -> None:
        src = """
def f(x):
    if x > 0:
        return x
    else:
        return -x
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        # Equivalent to abs(x)
        s = z3.Solver()
        s.add(z3.Or(
            z3.And(x == -3, expr != 3),
            z3.And(x == 5, expr != 5),
        ))
        assert s.check() == z3.unsat

    def test_if_elif_else(self) -> None:
        """Clamp pattern: the canonical test case."""
        src = """
def f(val, lo, hi):
    if val < lo:
        return lo
    elif val > hi:
        return hi
    else:
        return val
"""
        val, lo, hi = z3.Real("val"), z3.Real("lo"), z3.Real("hi")
        expr = _translate(src, {"val": val, "lo": lo, "hi": hi})
        s = z3.Solver()
        s.add(lo <= hi)
        # Postcondition: result is in [lo, hi]
        s.add(z3.Not(z3.And(expr >= lo, expr <= hi)))
        assert s.check() == z3.unsat

    def test_early_return(self) -> None:
        src = """
def f(x):
    if x < 0:
        return 0
    return x
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        # Should be max(x, 0)
        s = z3.Solver()
        s.add(z3.Or(
            z3.And(x == -5, expr != 0),
            z3.And(x == 5, expr != 5),
        ))
        assert s.check() == z3.unsat

    def test_if_no_else_with_remainder(self) -> None:
        src = """
def f(x):
    y = x
    if x < 0:
        y = -x
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        # Equivalent to abs(x)
        s = z3.Solver()
        s.add(x == -7)
        s.add(expr != 7)
        assert s.check() == z3.unsat

    def test_nested_if(self) -> None:
        src = """
def f(x, y):
    if x > 0:
        if y > 0:
            return x + y
        else:
            return x - y
    else:
        return -x
"""
        x, y = z3.Real("x"), z3.Real("y")
        expr = _translate(src, {"x": x, "y": y})
        s = z3.Solver()
        s.add(x == 3, y == 2)
        s.add(expr != 5)
        assert s.check() == z3.unsat


# ---------------------------------------------------------------------------
# Closure variable resolution
# ---------------------------------------------------------------------------


class TestClosureVars:
    def test_module_constant_resolved(self) -> None:
        """Translator.closure_vars should substitute numeric constants."""
        src = """
def f(x):
    return x + LIMIT
"""
        x = z3.Real("x")
        t = Translator(closure_vars={"LIMIT": z3.RealVal("10")})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

        s = z3.Solver()
        s.add(x == 5)
        s.add(result.return_expr != 15)
        assert s.check() == z3.unsat

    def test_closure_int_constant(self) -> None:
        """Integer closure constant uses IntVal."""
        src = """
def f(n):
    return n + BASE
"""
        n = z3.Int("n")
        t = Translator(closure_vars={"BASE": z3.IntVal(100)})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {"n": n})
        assert result.return_expr is not None

        s = z3.Solver()
        s.add(n == 7)
        s.add(result.return_expr != 107)
        assert s.check() == z3.unsat

    def test_shadowed_variable_local_wins(self) -> None:
        """A local variable with the same name as a closure var shadows it."""
        src = """
def f(x):
    LIMIT = x * 2
    return LIMIT
"""
        x = z3.Real("x")
        # Even with a closure var named LIMIT, the local assignment wins
        t = Translator(closure_vars={"LIMIT": z3.RealVal("999")})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

        s = z3.Solver()
        s.add(x == 3)
        # Result should be 6 (x * 2), not 999
        s.add(result.return_expr != 6)
        assert s.check() == z3.unsat

    def test_closure_bool_constant(self) -> None:
        """Boolean closure constant uses BoolVal."""
        src = """
def f(x):
    return FLAG
"""
        t = Translator(closure_vars={"FLAG": z3.BoolVal(True)})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {})
        assert result.return_expr is not None
        assert z3.is_true(result.return_expr)


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


class TestCoercion:
    def test_int_real_mixed(self) -> None:
        src = """
def f(x):
    return x + 1
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        # 1 is IntVal, x is Real — should coerce
        s = z3.Solver()
        s.add(x == 2.5)
        s.add(expr != 3.5)
        assert s.check() == z3.unsat

    def test_int_int(self) -> None:
        src = """
def f(x):
    return x + 1
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        assert expr.sort() == z3.IntSort()


# ---------------------------------------------------------------------------
# Unsupported constructs
# ---------------------------------------------------------------------------


UNSUPPORTED_CONSTRUCTS = [
    pytest.param(
        """
def f(x):
    while x > 0:
        x -= 1
    return x
""",
        id="while_loop",
    ),
    pytest.param(
        """
def f(x):
    with open("file") as fh:
        return fh.read()
""",
        id="with_statement",
    ),
    pytest.param(
        """
def f(x):
    try:
        return 1 / x
    except ZeroDivisionError:
        return 0
""",
        id="try_except",
    ),
    pytest.param(
        """
def f(x):
    yield x
""",
        id="yield",
    ),
    pytest.param(
        """
def f(x):
    return [i for i in range(x)]
""",
        id="list_comprehension",
    ),
]


@pytest.mark.parametrize("source", UNSUPPORTED_CONSTRUCTS)
def test_unsupported_construct_raises_or_warns(source: str) -> None:
    """Unsupported statements should either raise TranslationError or produce a warning."""
    x = z3.Real("x")
    func_ast = _parse_func(source)
    t = Translator()
    try:
        result = t.translate(func_ast, {"x": x})
        # If no exception, at least a warning should have been emitted
        assert result.warnings, (
            f"Expected warning for unsupported construct but got none. "
            f"Return expr: {result.return_expr}"
        )
    except TranslationError:
        pass  # Acceptable — construct explicitly rejected


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_undefined_variable(self) -> None:
        src = """
def f(x):
    return y
"""
        x = z3.Real("x")
        with pytest.raises(TranslationError, match="Undefined variable"):
            _translate(src, {"x": x})

    def test_unknown_function(self) -> None:
        src = """
def f(x):
    return foo(x)
"""
        x = z3.Real("x")
        with pytest.raises(TranslationError, match="Unknown function"):
            _translate(src, {"x": x})

    def test_unsupported_power(self) -> None:
        src = """
def f(x, n):
    return x ** n
"""
        x, n = z3.Real("x"), z3.Real("n")
        with pytest.raises(TranslationError, match="constant integer exponents"):
            _translate(src, {"x": x, "n": n})
