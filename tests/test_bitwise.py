"""Tests for bitwise operators: & | ^ << >>."""

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


def _assert_eq(expr: z3.ExprRef, expected: int, bindings: dict[str, int]) -> None:
    s = z3.Solver()
    for name, val in bindings.items():
        s.add(z3.Int(name) == val)
    s.add(expr != expected)
    assert s.check() == z3.unsat, (
        f"Expected {expr} == {expected} under {bindings}, got {s.check()}"
    )


class TestBitAnd:
    def test_bitand_concrete(self) -> None:
        src = "def f(x, y): return x & y"
        x, y = z3.Int("x"), z3.Int("y")
        expr = _translate(src, {"x": x, "y": y})
        _assert_eq(expr, 2, {"x": 6, "y": 3})  # 6 & 3 == 2

    def test_bitand_mask(self) -> None:
        src = "def f(x): return x & 255"
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 300)
        s.add(expr != 44)  # 300 & 255 = 44
        assert s.check() == z3.unsat


class TestBitOr:
    def test_bitor_concrete(self) -> None:
        src = "def f(x, y): return x | y"
        x, y = z3.Int("x"), z3.Int("y")
        expr = _translate(src, {"x": x, "y": y})
        _assert_eq(expr, 7, {"x": 6, "y": 3})  # 6 | 3 == 7


class TestBitXor:
    def test_bitxor_concrete(self) -> None:
        src = "def f(x, y): return x ^ y"
        x, y = z3.Int("x"), z3.Int("y")
        expr = _translate(src, {"x": x, "y": y})
        _assert_eq(expr, 5, {"x": 6, "y": 3})  # 6 ^ 3 == 5

    def test_bitxor_self_is_zero(self) -> None:
        src = "def f(x): return x ^ x"
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        # For any concrete x >= 0 and < 2**63, x XOR x == 0
        s = z3.Solver()
        s.add(x == 42)
        s.add(expr != 0)
        assert s.check() == z3.unsat


class TestLShift:
    def test_lshift_concrete(self) -> None:
        src = "def f(x): return x << 2"
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 5)
        s.add(expr != 20)  # 5 << 2 == 20
        assert s.check() == z3.unsat


class TestRShift:
    def test_rshift_concrete(self) -> None:
        src = "def f(x): return x >> 2"
        x = z3.Int("x")
        expr = _translate(src, {"x": x})
        s = z3.Solver()
        s.add(x == 20)
        s.add(expr != 5)  # 20 >> 2 == 5
        assert s.check() == z3.unsat


class TestBitwiseInVerified:
    def test_bitand_identity_via_mask_verifies(self) -> None:
        from provably import verified

        @verified(
            pre=lambda x: (x >= 0) & (x < 256),
            post=lambda x, result: result == x,
            timeout_ms=30000,
        )
        def identity_via_bitand(x: int) -> int:
            return x & 255

        assert identity_via_bitand.__proof__.verified  # type: ignore[attr-defined]

    def test_lshift_equals_mul_by_two_verifies(self) -> None:
        from provably import verified

        @verified(
            pre=lambda x: (x >= 0) & (x < 1024),
            post=lambda x, result: result == 2 * x,
            timeout_ms=30000,
        )
        def double_via_lshift(x: int) -> int:
            return x << 1

        assert double_via_lshift.__proof__.verified  # type: ignore[attr-defined]


class TestBitwiseErrors:
    def test_bitand_on_float_raises(self) -> None:
        src = "def f(x, y): return x & y"
        x, y = z3.Real("x"), z3.Real("y")
        with pytest.raises(TranslationError, match="integer operands"):
            _translate(src, {"x": x, "y": y})
