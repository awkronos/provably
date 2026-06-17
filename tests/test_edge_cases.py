"""Edge case tests covering uncovered paths and new builtins.

Tests for:
  - sum/any/all builtin support
  - None pre/post conditions
  - min/max builtins
  - augmented assignment
  - certificate explain()
  - while loop bounded verification
"""

from __future__ import annotations

import ast
import textwrap

import pytest
import z3

from provably.translator import TranslationError, Translator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_func(source: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    return tree.body[0]  # type: ignore[return-value]


def _translate(source: str, param_vars: dict[str, z3.ExprRef]) -> z3.ExprRef:
    func_ast = _parse_func(source)
    t = Translator()
    result = t.translate(func_ast, param_vars)
    assert result.return_expr is not None, f"No return expression: {result.warnings}"
    return result.return_expr


# ---------------------------------------------------------------------------
# sum() support
# ---------------------------------------------------------------------------


class TestSumBuiltin:
    def test_sum_list_literal_ints(self) -> None:
        x = z3.Int("x")
        src = """
def f(x):
    return sum([x, 1, 2])
"""
        expr = _translate(src, {"x": x})
        # sum([x, 1, 2]) == x + 1 + 2 == x + 3
        s = z3.Solver()
        s.add(expr != x + 3)
        assert s.check() == z3.unsat

    def test_sum_empty_list_is_zero(self) -> None:
        src = """
def f():
    return sum([])
"""
        expr = _translate(src, {})
        assert z3.is_int_value(expr) and expr.as_long() == 0

    def test_sum_generator_range(self) -> None:
        # sum(i for i in range(4)) == 0+1+2+3 == 6
        src = """
def f():
    return sum(i for i in range(4))
"""
        expr = _translate(src, {})
        simplified = z3.simplify(expr)
        assert z3.is_int_value(simplified) and simplified.as_long() == 6

    def test_sum_generator_expression_with_offset(self) -> None:
        # sum(i*2 for i in range(3)) == 0+2+4 == 6
        src = """
def f():
    return sum(i * 2 for i in range(3))
"""
        expr = _translate(src, {})
        simplified = z3.simplify(expr)
        assert z3.is_int_value(simplified) and simplified.as_long() == 6

    def test_sum_list_two_vars(self) -> None:
        a = z3.Int("a")
        b = z3.Int("b")
        src = """
def f(a, b):
    return sum([a, b])
"""
        expr = _translate(src, {"a": a, "b": b})
        s = z3.Solver()
        s.add(expr != a + b)
        assert s.check() == z3.unsat

    def test_sum_generator_unsupported_raises(self) -> None:
        # sum over a non-range iterator should raise
        src = """
def f(x):
    return sum(x for x in [1, 2, 3])
"""
        with pytest.raises(TranslationError, match="sum\\(\\)"):
            _translate(src, {})

    def test_sum_range_zero_iterations(self) -> None:
        # sum(i for i in range(0)) == 0
        src = """
def f():
    return sum(i for i in range(0))
"""
        expr = _translate(src, {})
        simplified = z3.simplify(expr)
        assert z3.is_int_value(simplified) and simplified.as_long() == 0


# ---------------------------------------------------------------------------
# any() support
# ---------------------------------------------------------------------------


class TestAnyBuiltin:
    def test_any_list_literal_true(self) -> None:
        src = """
def f():
    return any([True, False])
"""
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_any_list_literal_false(self) -> None:
        src = """
def f():
    return any([False, False])
"""
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_any_empty_list_is_false(self) -> None:
        src = """
def f():
    return any([])
"""
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_any_symbolic(self) -> None:
        a = z3.Bool("a")
        b = z3.Bool("b")
        src = """
def f(a, b):
    return any([a, b])
"""
        expr = _translate(src, {"a": a, "b": b})
        # should be Or(a, b)
        s = z3.Solver()
        s.add(expr != z3.Or(a, b))
        assert s.check() == z3.unsat

    def test_any_generator_raises(self) -> None:
        src = """
def f():
    return any(x > 0 for x in [1, 2])
"""
        with pytest.raises(TranslationError, match="any\\(\\)"):
            _translate(src, {})


# ---------------------------------------------------------------------------
# all() support
# ---------------------------------------------------------------------------


class TestAllBuiltin:
    def test_all_list_literal_true(self) -> None:
        src = """
def f():
    return all([True, True])
"""
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_all_list_literal_false(self) -> None:
        src = """
def f():
    return all([True, False])
"""
        expr = _translate(src, {})
        assert z3.is_false(z3.simplify(expr))

    def test_all_empty_list_is_true(self) -> None:
        src = """
def f():
    return all([])
"""
        expr = _translate(src, {})
        assert z3.is_true(z3.simplify(expr))

    def test_all_symbolic(self) -> None:
        a = z3.Bool("a")
        b = z3.Bool("b")
        src = """
def f(a, b):
    return all([a, b])
"""
        expr = _translate(src, {"a": a, "b": b})
        s = z3.Solver()
        s.add(expr != z3.And(a, b))
        assert s.check() == z3.unsat

    def test_all_generator_raises(self) -> None:
        src = """
def f():
    return all(x > 0 for x in [1, 2])
"""
        with pytest.raises(TranslationError, match="all\\(\\)"):
            _translate(src, {})


# ---------------------------------------------------------------------------
# @verified decorator edge cases
# ---------------------------------------------------------------------------


class TestVerifiedDecoratorEdgeCases:
    def test_min_max_builtins(self) -> None:
        """min(a, b) returns a value <= both arguments."""
        from provably import verified

        @verified(
            pre=None,
            post=lambda a, b, result: (result <= a) & (result <= b),
        )
        def my_min(a: int, b: int) -> int:
            return min(a, b)

        assert my_min.__proof__.verified  # type: ignore[attr-defined]

    def test_augmented_assignment(self) -> None:
        """x += x += x produces 3*x."""
        from provably import verified

        @verified(pre=lambda x: x >= 0, post=lambda x, result: result == 3 * x)
        def triple(x: int) -> int:
            r = x
            r += x
            r += x
            return r

        assert triple.__proof__.verified  # type: ignore[attr-defined]

    def test_certificate_explain_nonempty(self) -> None:
        from provably import verified

        @verified(pre=lambda x: x > 0, post=lambda r, x: r > 0)
        def pos(x: int) -> int:
            return x

        expl = pos.__proof__.explain()  # type: ignore[attr-defined]
        assert isinstance(expl, str)
        assert len(expl) > 0

    def test_while_loop_bounded(self) -> None:
        """Bounded while-loop: countdown from n to 0."""
        from provably import verified

        # pre uses & not `and` to avoid Z3 symbolic bool Python-bool coercion error.
        @verified(
            pre=lambda n: (n >= 0) & (n <= 10),
            post=lambda n, result: result == 0,
        )
        def countdown(n: int) -> int:
            i = n
            while i > 0:
                i -= 1
            return i

        assert countdown.__proof__.verified  # type: ignore[attr-defined]

    def test_none_pre_post(self) -> None:
        """No pre/post: nothing to prove, status is SKIPPED (not an error)."""
        from provably import Status, verified

        @verified(pre=None, post=None)
        def identity(x: int) -> int:
            return x

        # When post=None there is nothing to prove; engine returns SKIPPED.
        assert identity.__proof__.status == Status.SKIPPED  # type: ignore[attr-defined]

    def test_proof_certificate_has_status(self) -> None:
        from provably import Status, verified

        @verified(pre=lambda x: x >= 0, post=lambda r, x: r >= 0)
        def nonneg(x: int) -> int:
            return x

        cert = nonneg.__proof__  # type: ignore[attr-defined]
        assert cert.status == Status.VERIFIED

    def test_sum_list_in_verified(self) -> None:
        """sum([a, b]) inside @verified should translate and verify."""
        from provably import verified

        @verified(
            pre=None,
            post=lambda a, b, result: result == a + b,
        )
        def add_via_sum(a: int, b: int) -> int:
            return sum([a, b])

        assert add_via_sum.__proof__.verified  # type: ignore[attr-defined]

    def test_any_all_in_verified(self) -> None:
        """any([]) and all([]) should at least not crash during translation."""
        from provably import verified

        @verified(pre=None, post=None)
        def any_empty() -> bool:
            return any([])

        @verified(pre=None, post=None)
        def all_empty() -> bool:
            return all([])

        assert any_empty.__proof__ is not None  # type: ignore[attr-defined]
        assert all_empty.__proof__ is not None  # type: ignore[attr-defined]
