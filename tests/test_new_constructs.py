"""Tests for new translator constructs: while, walrus, match/case, tuple, subscript, casts."""

from __future__ import annotations

import ast
import sys
import textwrap

import pytest
import z3

from provably import Status, verified, verify_function
from provably._self_proof import (
    SELF_PROOFS,
    abs_via_walrus,
    bool_cast_test,
    double_bounded,
    float_cast_nonneg,
    square_via_pow,
    while_countdown,
)
from provably.translator import TranslationError, Translator


class TestWhileLoops:
    """Tests for bounded while-loop unrolling."""

    def test_simple_countdown(self) -> None:
        def countdown(x: int) -> int:
            while x > 0:
                x = x - 1
            return x

        cert = verify_function(countdown, pre=lambda x: (x >= 0) & (x <= 10), post=lambda x, result: result == 0)
        assert cert.verified, cert.message

    def test_while_with_accumulator(self) -> None:
        def sum_to_n(n: int) -> int:
            total = 0
            i = 0
            while i < n:
                total = total + i
                i = i + 1
            return total

        cert = verify_function(sum_to_n, pre=lambda n: (n >= 0) & (n <= 5), post=lambda n, result: result >= 0)
        assert cert.verified, cert.message

    def test_while_false_never_enters(self) -> None:
        def never_loop(x: float) -> float:
            while False:
                x = x + 1
            return x

        cert = verify_function(never_loop, post=lambda x, result: result == x)
        assert cert.verified, cert.message

    def test_while_translator_direct(self) -> None:
        src = """
def f(x):
    while x > 0:
        x = x - 1
    return x
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None


class TestWalrusOperator:
    """Tests for := (NamedExpr) support."""

    def test_walrus_in_ternary(self) -> None:
        def abs_walrus(x: float) -> float:
            return (neg := -x) if x < 0 else x

        cert = verify_function(abs_walrus, post=lambda x, result: (result >= 0) & ((result == x) | (result == -x)))
        assert cert.verified, cert.message

    def test_walrus_translator_direct(self) -> None:
        src = """
def f(x):
    return (y := x + 1)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        # y should be in environment
        assert "y" in result.env


class TestTupleReturns:
    """Tests for tuple expression support."""

    def test_tuple_return_translator(self) -> None:
        src = """
def f(x):
    return (x, x + 1)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        # Should have accessor constraints
        assert len(result.constraints) >= 2

    def test_singleton_tuple_is_unwrapped(self) -> None:
        src = """
def f(x):
    return (x,)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        # Singleton tuple should be unwrapped to just x
        assert result.return_expr is x


class TestConstantSubscript:
    """Tests for arr[0]-style constant subscript access."""

    def test_subscript_on_non_tuple_raises(self) -> None:
        src = """
def f(x):
    return x[0]
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="non-tuple"):
            t.translate(func_ast, {"x": x})

    def test_variable_subscript_raises(self) -> None:
        src = """
def f(x, i):
    return x[i]
"""
        x = z3.Int("x")
        i = z3.Int("i")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="constant integer"):
            t.translate(func_ast, {"x": x, "i": i})


class TestMatchCase:
    """Tests for match/case statement support (Python 3.10+)."""

    @pytest.mark.skipif(sys.version_info < (3, 10), reason="match/case requires Python 3.10+")
    def test_simple_match(self) -> None:
        src = """
def f(x):
    match x:
        case 1:
            return 10
        case 2:
            return 20
        case _:
            return 0
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None


class TestNewBuiltins:
    """Tests for pow, bool, int, float, len, round builtins."""

    def test_pow_builtin(self) -> None:
        def square(x: float) -> float:
            return pow(x, 2)

        cert = verify_function(square, pre=lambda x: x >= 0, post=lambda x, result: result >= 0)
        assert cert.verified, cert.message

    def test_bool_cast(self) -> None:
        src = """
def f(x):
    return bool(x)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

    def test_int_cast(self) -> None:
        src = """
def f(x):
    return int(x)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        assert result.return_expr.sort() == z3.IntSort()

    def test_float_cast(self) -> None:
        src = """
def f(x):
    return float(x)
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        assert result.return_expr.sort() == z3.RealSort()

    def test_len_builtin(self) -> None:
        src = """
def f(x):
    return len(x)
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        # len should add non-negativity constraint
        assert any("0" in str(c) for c in result.constraints)

    def test_round_builtin(self) -> None:
        src = """
def f(x):
    return round(x)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        assert result.return_expr.sort() == z3.IntSort()


class TestTupleUnpacking:
    """Tests for tuple unpacking in assignments."""

    def test_tuple_unpack_translator(self) -> None:
        src = """
def f(x):
    a, b = (x, x + 1)
    return a
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        assert "a" in result.env
        assert "b" in result.env


class TestSelfProofsExpanded:
    """Verify all self-proof functions (original + new) are VERIFIED."""

    def test_all_self_proofs_verified(self) -> None:
        for fn in SELF_PROOFS:
            cert = getattr(fn, "__proof__", None)
            assert cert is not None, f"{fn.__name__}: no __proof__ attribute"
            assert cert.verified, f"{fn.__name__}: {cert.status.value} — {cert.message}"

    def test_self_proof_count(self) -> None:
        assert len(SELF_PROOFS) == 16, f"Expected 16 self-proofs, got {len(SELF_PROOFS)}"

    def test_while_countdown_verified(self) -> None:
        assert while_countdown.__proof__.verified

    def test_square_via_pow_verified(self) -> None:
        assert square_via_pow.__proof__.verified

    def test_abs_via_walrus_verified(self) -> None:
        assert abs_via_walrus.__proof__.verified

    def test_float_cast_nonneg_verified(self) -> None:
        assert float_cast_nonneg.__proof__.verified

    def test_bool_cast_test_verified(self) -> None:
        assert bool_cast_test.__proof__.verified

    def test_double_bounded_verified(self) -> None:
        assert double_bounded.__proof__.verified

    def test_while_countdown_runtime(self) -> None:
        assert while_countdown(0) == 0
        assert while_countdown(5) == 0
        assert while_countdown(10) == 0

    def test_square_via_pow_runtime(self) -> None:
        assert square_via_pow(3.0) == 9.0
        assert square_via_pow(0.0) == 0.0

    def test_abs_via_walrus_runtime(self) -> None:
        assert abs_via_walrus(-5.0) == 5.0
        assert abs_via_walrus(3.0) == 3.0

    def test_float_cast_runtime(self) -> None:
        assert float_cast_nonneg(42) == 42.0

    def test_double_bounded_runtime(self) -> None:
        assert double_bounded(3) == 6
        assert double_bounded(5) == 10
