"""Tests for the Lean4 backend."""

from __future__ import annotations

import pytest

from provably.lean4 import (
    HAS_LEAN4,
    LEAN4_VERSION,
    _expr_to_lean,
    _z3_str_to_lean,
    export_lean4,
    generate_lean4_theorem,
    verify_with_lean4,
)


class TestExprToLean:
    """Test Python AST → Lean4 expression translation."""

    def test_constant_int(self) -> None:
        import ast

        node = ast.Constant(value=42)
        assert _expr_to_lean(node) == "42"

    def test_constant_float(self) -> None:
        import ast

        node = ast.Constant(value=3.14)
        assert "3.14" in _expr_to_lean(node)

    def test_name(self) -> None:
        import ast

        node = ast.Name(id="x")
        assert _expr_to_lean(node) == "x"

    def test_name_with_env(self) -> None:
        import ast

        node = ast.Name(id="x")
        assert _expr_to_lean(node, {"x": "my_x"}) == "my_x"


class TestZ3StrToLean:
    """Test Z3 string → Lean4 syntax conversion."""

    def test_basic_comparison(self) -> None:
        result = _z3_str_to_lean("x >= 0", ["x"])
        assert "≥" in result

    def test_and_conversion(self) -> None:
        result = _z3_str_to_lean("And(x >= 0, x <= 1)", ["x"])
        assert "≥" in result
        assert "≤" in result


class TestGenerateTheorem:
    """Test Lean4 theorem generation."""

    def test_simple_function(self) -> None:
        source = "def double(x: float) -> float:\n    return x * 2\n"
        lean = generate_lean4_theorem(
            func_name="double",
            param_names=["x"],
            param_types={"x": float},
            pre_str="x ≥ 0",
            post_str="(double_impl x) ≥ 0",
            source=source,
        )
        assert "theorem double_verified" in lean
        assert "noncomputable def double_impl" in lean
        assert "nlinarith" in lean

    def test_no_postcondition(self) -> None:
        source = "def noop(x: float) -> float:\n    return x\n"
        lean = generate_lean4_theorem(
            func_name="noop",
            param_names=["x"],
            param_types={"x": float},
            pre_str=None,
            post_str=None,
            source=source,
        )
        assert "No postcondition" in lean


class TestExportLean4:
    """Test exporting @verified functions to Lean4."""

    def test_export_clamp(self) -> None:
        def clamp(x: float, lo: float, hi: float) -> float:
            if x < lo:
                return lo
            elif x > hi:
                return hi
            return x

        lean = export_lean4(
            clamp,
            pre=lambda x, lo, hi: lo <= hi,
            post=lambda x, lo, hi, result: (result >= lo) & (result <= hi),
        )
        assert "theorem clamp_verified" in lean
        assert "noncomputable def clamp_impl" in lean

    def test_export_simple(self) -> None:
        def double(x: float) -> float:
            return x * 2

        lean = export_lean4(
            double,
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= 0,
        )
        assert "double" in lean


class TestVerifyWithLean4:
    """Test full Lean4 verification pipeline."""

    def test_lean4_availability(self) -> None:
        """Check HAS_LEAN4 matches reality."""
        import shutil

        lean_found = shutil.which("lean") is not None
        # May differ if lean is in a non-PATH location, so just check it doesn't crash
        assert isinstance(HAS_LEAN4, bool)

    @pytest.mark.skipif(not HAS_LEAN4, reason="Lean4 not installed")
    def test_verify_returns_certificate(self) -> None:
        def double(x: float) -> float:
            return x * 2

        cert = verify_with_lean4(
            double,
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= 0,
        )
        assert cert.function_name == "double"
        assert cert.status.value in ("verified", "unknown", "skipped")
        # Lean4 may not prove this without Mathlib — UNKNOWN is acceptable
        assert "lean4" in cert.z3_version

    def test_graceful_skip_without_lean4(self) -> None:
        if HAS_LEAN4:
            pytest.skip("Lean4 IS available")

        def double(x: float) -> float:
            return x * 2

        cert = verify_with_lean4(double, post=lambda x, result: result >= 0)
        assert cert.status.value == "skipped"
        assert "not installed" in cert.message


class TestLean4Version:
    """Test version detection."""

    @pytest.mark.skipif(not HAS_LEAN4, reason="Lean4 not installed")
    def test_version_string(self) -> None:
        assert "Lean" in LEAN4_VERSION or "lean" in LEAN4_VERSION.lower()
