"""Translator edge cases — AST → Z3 constraint translation."""

from __future__ import annotations

import ast
import textwrap

import pytest
from conftest import requires_z3

pytestmark = requires_z3

import z3

from provably.translator import TranslationError, Translator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_func(source: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    return tree.body[0]  # type: ignore[return-value]


def _translate(
    source: str,
    param_vars: dict[str, z3.ExprRef],
    closure_vars: dict[str, z3.ExprRef] | None = None,
) -> z3.ExprRef:
    """Translate source and return the return expression."""
    func_ast = _parse_func(source)
    t = Translator(closure_vars=closure_vars or {})
    result = t.translate(func_ast, param_vars)
    assert result.return_expr is not None, f"No return: {result.warnings}"
    return result.return_expr


def _sat(solver: z3.Solver) -> bool:
    return solver.check() == z3.sat


def _unsat(solver: z3.Solver) -> bool:
    return solver.check() == z3.unsat


# ---------------------------------------------------------------------------
# Power operator edge cases
# ---------------------------------------------------------------------------


class TestPowerExponent:
    def test_power_exponent_0(self) -> None:
        """x**0 == 1 for integer x."""
        src = """
def f(x):
    return x ** 0
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(expr != 1)
        assert _unsat(s)

    def test_power_exponent_1(self) -> None:
        """x**1 == x."""
        src = """
def f(x):
    return x ** 1
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(expr != x)
        assert _unsat(s)

    def test_power_exponent_2(self) -> None:
        """x**2 == x*x."""
        src = """
def f(x):
    return x ** 2
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr != 25)
        assert _unsat(s)

    def test_power_exponent_3(self) -> None:
        """x**3 == x*x*x."""
        src = """
def f(x):
    return x ** 3
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 3)
        s.add(expr != 27)
        assert _unsat(s)

    def test_power_float_exponent_0(self) -> None:
        """x**0 with Real x raises TranslationError.

        The translator coerces Int exponent to Real (via _coerce in _binop),
        which causes is_int_value(exp) to fail in _pow. This is a known
        limitation: ** with Real operands requires the exponent to remain Int.
        """
        src = """
def f(x):
    return x ** 0
"""
        x = z3.Real("x")
        func_ast = _parse_func(src)
        t = Translator()
        with pytest.raises(TranslationError, match="constant integer exponents"):
            t.translate(func_ast, {"x": x})


# ---------------------------------------------------------------------------
# Integer floor division and modulo
# ---------------------------------------------------------------------------


class TestIntegerDivMod:
    def test_integer_floor_division(self) -> None:
        """7 // 2 == 3 in Z3 integer division."""
        src = """
def f(x):
    return x // 2
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 7)
        s.add(expr != 3)
        assert _unsat(s)

    def test_integer_modulo(self) -> None:
        """7 % 3 == 1."""
        src = """
def f(x):
    return x % 3
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 7)
        s.add(expr != 1)
        assert _unsat(s)

    def test_floor_div_exact(self) -> None:
        """10 // 5 == 2."""
        src = """
def f(x):
    return x // 5
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 10)
        s.add(expr != 2)
        assert _unsat(s)

    def test_modulo_zero_remainder(self) -> None:
        """9 % 3 == 0."""
        src = """
def f(x):
    return x % 3
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 9)
        s.add(expr != 0)
        assert _unsat(s)


# ---------------------------------------------------------------------------
# Boolean not
# ---------------------------------------------------------------------------


class TestBoolNot:
    def test_bool_not(self) -> None:
        """not True == False."""
        src = """
def f(x):
    return not (x > 0)
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        # When x = 5, not (5 > 0) = not True = False
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr)  # expr should be False — adding it and checking sat
        assert _unsat(s)

    def test_bool_not_false_is_true(self) -> None:
        """not (x > 0) when x <= 0 is True."""
        src = """
def f(x):
    return not (x > 0)
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == -1)
        s.add(z3.Not(expr))  # expr should be True, so Not(expr) should be unsat
        assert _unsat(s)


# ---------------------------------------------------------------------------
# Unary plus
# ---------------------------------------------------------------------------


class TestUnaryPlus:
    def test_unary_plus(self) -> None:
        """+x == x."""
        src = """
def f(x):
    return +x
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(expr != x)
        assert _unsat(s)

    def test_unary_plus_int(self) -> None:
        """+n == n for integers."""
        src = """
def f(n):
    return +n
"""
        n = z3.Int("n")
        expr = _translate(src, {"n": n})
        s = z3.Solver()
        s.add(n == 42)
        s.add(expr != 42)
        assert _unsat(s)


# ---------------------------------------------------------------------------
# Annotated assignment
# ---------------------------------------------------------------------------


class TestAnnAssign:
    def test_ann_assign_with_value(self) -> None:
        """`y: int = x + 1` binds y."""
        src = """
def f(x):
    y: int = x + 1
    return y
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 10)
        s.add(expr != 11)
        assert _unsat(s)

    def test_ann_assign_without_value(self) -> None:
        """`y: int` with no value is skipped (no binding produced)."""
        src = """
def f(x):
    y: int
    y = x + 2
    return y
"""
        x = z3.Int("x")
        # Should not raise — the bare annotation is skipped
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr != 7)
        assert _unsat(s)


# ---------------------------------------------------------------------------
# Multiple assert statements
# ---------------------------------------------------------------------------


class TestMultipleAsserts:
    def test_multiple_asserts(self) -> None:
        """Two assert statements both become constraints."""
        src = """
def f(x):
    assert x > 0
    assert x < 100
    return x
"""
        x = z3.Real("x")
        func_ast = _parse_func(src)
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert len(result.constraints) == 2

    def test_single_assert_constraint(self) -> None:
        """One assert → one constraint."""
        src = """
def f(x):
    assert x >= 0
    return x
"""
        x = z3.Real("x")
        func_ast = _parse_func(src)
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert len(result.constraints) == 1


# ---------------------------------------------------------------------------
# For loop unrolling
# ---------------------------------------------------------------------------


class TestForLoopRange:
    def test_for_loop_range_1_arg(self) -> None:
        """for i in range(5): x += i  →  x += 0+1+2+3+4 = 10."""
        src = """
def f(x):
    for i in range(5):
        x += i
    return x
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 0)
        s.add(expr != 10)
        assert _unsat(s)

    def test_for_loop_range_2_args(self) -> None:
        """for i in range(2, 5): x += i  →  x += 2+3+4 = 9."""
        src = """
def f(x):
    for i in range(2, 5):
        x += i
    return x
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 0)
        s.add(expr != 9)
        assert _unsat(s)

    def test_for_loop_range_3_args(self) -> None:
        """for i in range(0, 10, 2): x += i  →  x += 0+2+4+6+8 = 20."""
        src = """
def f(x):
    for i in range(0, 10, 2):
        x += i
    return x
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 0)
        s.add(expr != 20)
        assert _unsat(s)

    def test_for_loop_too_large(self) -> None:
        """range(1000) exceeds _MAX_UNROLL=256 → TranslationError."""
        src = """
def f(x):
    for i in range(1000):
        x += i
    return x
"""
        x = z3.Int("x")
        func_ast = _parse_func(src)
        t = Translator()
        with pytest.raises(TranslationError, match="max is"):
            t.translate(func_ast, {"x": x})

    def test_for_loop_empty_range(self) -> None:
        """for i in range(0): body never executes, x unchanged."""
        src = """
def f(x):
    for i in range(0):
        x += 1
    return x
"""
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 7)
        s.add(expr != 7)
        assert _unsat(s)


# ---------------------------------------------------------------------------
# Unsupported constructs → error or warning
# ---------------------------------------------------------------------------


class TestUnsupportedConstructs:
    def test_while_loop_unsupported(self) -> None:
        """while loops produce a warning (unsupported statement)."""
        src = """
def f(x):
    while x > 0:
        x -= 1
    return x
"""
        x = z3.Real("x")
        func_ast = _parse_func(src)
        t = Translator()
        try:
            result = t.translate(func_ast, {"x": x})
            # Must have a warning about the unsupported while loop
            assert result.warnings, "Expected warning for while loop"
            assert any("While" in w or "while" in w.lower() for w in result.warnings)
        except TranslationError:
            pass  # Also acceptable

    def test_with_statement_unsupported(self) -> None:
        """with statements produce a warning (unsupported statement)."""
        src = """
def f(x):
    with open("file") as fh:
        return x
"""
        x = z3.Real("x")
        func_ast = _parse_func(src)
        t = Translator()
        try:
            result = t.translate(func_ast, {"x": x})
            assert result.warnings, "Expected warning for with statement"
        except TranslationError:
            pass

    def test_list_comprehension_unsupported(self) -> None:
        """List comprehensions raise TranslationError or emit a warning."""
        src = """
def f(x):
    return [i for i in range(x)]
"""
        x = z3.Real("x")
        func_ast = _parse_func(src)
        t = Translator()
        try:
            result = t.translate(func_ast, {"x": x})
            assert result.warnings, "Expected warning for list comprehension"
        except TranslationError:
            pass  # Acceptable — comprehension explicitly rejected


# ---------------------------------------------------------------------------
# if-without-else with remainder
# ---------------------------------------------------------------------------


class TestIfNoElse:
    def test_if_no_else_assigns_variable(self) -> None:
        """if-without-else merges environments: both branches continue."""
        src = """
def f(x):
    y = 0
    if x > 0:
        y = x
    return y
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        # When x=5: y=5; when x=-3: y=0
        s1 = z3.Solver()
        s1.add(x == 5, expr != 5)
        assert _unsat(s1)

        s2 = z3.Solver()
        s2.add(x == -3, expr != 0)
        assert _unsat(s2)

    def test_if_no_else_with_multiple_variables(self) -> None:
        """Multiple variables in if-without-else are phi-merged."""
        src = """
def f(x):
    a = 1
    b = 2
    if x > 0:
        a = 10
        b = 20
    return a + b
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})
        s1 = z3.Solver()
        s1.add(x == 5, expr != 30)
        assert _unsat(s1)

        s2 = z3.Solver()
        s2.add(x == -1, expr != 3)
        assert _unsat(s2)


# ---------------------------------------------------------------------------
# Nested if with multiple returns
# ---------------------------------------------------------------------------


class TestNestedIf:
    def test_nested_if_with_multiple_returns(self) -> None:
        """3-level nested if with returns at each level."""
        src = """
def f(x):
    if x > 100:
        return 3
    elif x > 10:
        return 2
    else:
        return 1
"""
        x = z3.Real("x")
        expr = _translate(src, {"x": x})

        cases = [(200, 3), (50, 2), (5, 1)]
        for val, expected in cases:
            s = z3.Solver()
            s.add(x == val)
            s.add(expr != expected)
            assert _unsat(s), f"Failed for x={val}, expected={expected}"


# ---------------------------------------------------------------------------
# Chained comparison with four operands
# ---------------------------------------------------------------------------


class TestChainedComparisons:
    def test_chained_comparison_four_ops(self) -> None:
        """0 < x <= 10 < y — four-operand chained comparison."""
        src = """
def f(x, y):
    return 0 < x <= 10 < y
"""
        x = z3.Real("x")
        y = z3.Real("y")
        expr = _translate(src, {"x": x, "y": y})

        # x=5, y=20: 0 < 5 <= 10 < 20 → True
        s1 = z3.Solver()
        s1.add(x == 5, y == 20)
        s1.add(z3.Not(expr))
        assert _unsat(s1)

        # x=15, y=20: 0 < 15 <= 10 fails → False
        s2 = z3.Solver()
        s2.add(x == 15, y == 20)
        s2.add(expr)
        assert _unsat(s2)

        # x=5, y=10: 0 < 5 <= 10 < 10 fails (10 < 10 is False) → False
        s3 = z3.Solver()
        s3.add(x == 5, y == 10)
        s3.add(expr)
        assert _unsat(s3)


# ---------------------------------------------------------------------------
# Closure variable resolution edge cases
# ---------------------------------------------------------------------------


class TestClosureVarEdgeCases:
    def test_closure_var_float(self) -> None:
        """Module constant 3.14 resolved via closure_vars."""
        src = """
def f(x):
    return x + PI
"""
        x = z3.Real("x")
        t = Translator(closure_vars={"PI": z3.RealVal("3.14")})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

        s = z3.Solver()
        s.add(x == 0)
        s.add(result.return_expr != z3.RealVal("3.14"))
        assert _unsat(s)

    def test_closure_var_shadows_local(self) -> None:
        """Local assignment overrides the closure variable with the same name."""
        src = """
def f(x):
    LIMIT = x * 2
    return LIMIT
"""
        x = z3.Real("x")
        t = Translator(closure_vars={"LIMIT": z3.RealVal("999")})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

        s = z3.Solver()
        s.add(x == 3)
        # Result should be 6 (x * 2), not 999
        s.add(result.return_expr != 6)
        assert _unsat(s)

    def test_closure_var_int(self) -> None:
        """Integer closure constant."""
        src = """
def f(x):
    return x + BASE
"""
        x = z3.Int("x")
        t = Translator(closure_vars={"BASE": z3.IntVal(42)})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {"x": x})

        s = z3.Solver()
        s.add(x == 8)
        s.add(result.return_expr != 50)
        assert _unsat(s)

    def test_closure_var_bool(self) -> None:
        """Boolean closure constant."""
        src = """
def f(x):
    return FLAG
"""
        t = Translator(closure_vars={"FLAG": z3.BoolVal(True)})
        func_ast = _parse_func(src)
        result = t.translate(func_ast, {})
        assert z3.is_true(result.return_expr)
