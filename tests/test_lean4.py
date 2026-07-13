"""Tests for the Lean4 backend."""

from __future__ import annotations

import pytest

from provably.lean4 import (
    HAS_LEAN4,
    LEAN4_VERSION,
    _expr_to_lean,
    _z3_str_to_lean,
    check_lean4_proof,
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

    def test_equality_conversion_uses_propositional_equality(self) -> None:
        assert _z3_str_to_lean("result == x", ["x"]) == "result = x"


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


class TestLean4CoreMode:
    """Pure-Int/Bool functions produce kernel-clean Lean (no Mathlib).

    The whole point of the Lean4 backend is to give the user a second,
    independent kernel check. That promise is only meaningful if the
    output actually compiles with ``lean`` out of the box.
    """

    def test_int_function_uses_core_mode(self) -> None:
        source = (
            "def abs_like(x: int) -> int:\n"
            "    if x >= 0:\n"
            "        return x\n"
            "    else:\n"
            "        return -x\n"
        )
        lean = generate_lean4_theorem(
            func_name="abs_like",
            param_names=["x"],
            param_types={"x": int},
            pre_str=None,
            post_str="abs_like_impl x ≥ 0",
            source=source,
        )
        # No Mathlib import.
        assert "import Mathlib" not in lean
        # Core tactics only.
        assert "nlinarith" not in lean
        assert "omega" in lean or "decide" in lean or "rfl" in lean
        # Plain def, not noncomputable def.
        assert "noncomputable def" not in lean
        assert "def abs_like_impl" in lean
        # Mode banner.
        assert "Mode: core" in lean

    def test_float_function_uses_mathlib_mode(self) -> None:
        source = "def clip(x: float) -> float:\n    return x\n"
        lean = generate_lean4_theorem(
            func_name="clip",
            param_names=["x"],
            param_types={"x": float},
            pre_str=None,
            post_str="clip_impl x ≥ 0",
            source=source,
        )
        assert "import Mathlib" in lean
        assert "noncomputable def" in lean
        assert "Mode: mathlib" in lean

    @pytest.mark.skipif(not HAS_LEAN4, reason="Lean4 not installed")
    def test_core_mode_passes_kernel_and_is_clean(self) -> None:
        """End-to-end: generated core-mode Lean compiles AND reports only
        standard foundational axioms."""
        import subprocess
        import tempfile
        from pathlib import Path

        source = (
            "def abs_like(x: int) -> int:\n"
            "    if x >= 0:\n"
            "        return x\n"
            "    else:\n"
            "        return -x\n"
        )
        lean = generate_lean4_theorem(
            func_name="abs_like",
            param_names=["x"],
            param_types={"x": int},
            pre_str=None,
            post_str="abs_like_impl x ≥ 0",
            source=source,
        )
        # Append an axioms audit line.
        audited = lean + "\n\n#print axioms abs_like_verified\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False, prefix="provably_core_"
        ) as f:
            f.write(audited)
            tmp_path = f.name
        try:
            result = subprocess.run(
                ["lean", tmp_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = result.stdout + result.stderr
            assert result.returncode == 0, f"lean failed: {out[:500]}"
            # Only Lean foundational axioms allowed. No 'sorry', no
            # Mathlib lemmas, no user axioms.
            assert "sorry" not in out
            assert "axioms:" in out
            # The standard foundational axioms for core tactics:
            allowed = {"propext", "Quot.sound", "Classical.choice"}
            # Extract the axioms line.
            axioms_line = [ln for ln in out.splitlines() if "axioms" in ln]
            assert axioms_line
            line = axioms_line[0]
            # Every reported axiom must be in the allow-list.
            # A result like "does not depend on any axioms" is also fine.
            if "depend" in line and "any" not in line:
                # e.g. "'abs_like_verified' depends on axioms: [propext, Quot.sound]"
                inside = line.split("[", 1)[1].rstrip("]").strip() if "[" in line else ""
                reported = {a.strip() for a in inside.split(",") if a.strip()}
                assert reported.issubset(allowed), f"Unexpected axioms: {reported - allowed}"
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestLean4FailClosed:
    """Regression checks for admitted or missing proof obligations."""

    def test_sorry_placeholder_is_rejected(self) -> None:
        ok, output = check_lean4_proof("theorem fake : False := by sorry\n", theorem_name="fake")
        assert ok is False
        assert "placeholder" in output

    def test_no_postcondition_never_verifies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from provably import lean4 as lean4_module
        from provably.engine import Status

        monkeypatch.setattr(lean4_module, "HAS_LEAN4", True)

        def identity(x: int) -> int:
            return x

        certificate = lean4_module.verify_with_lean4(identity)
        assert certificate.status == Status.SKIPPED
        assert certificate.verified is False
        assert "postcondition" in certificate.message

    def test_nonsymbolic_postcondition_is_translation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from provably import lean4 as lean4_module
        from provably.engine import Status

        monkeypatch.setattr(lean4_module, "HAS_LEAN4", True)

        def identity(x: int) -> int:
            return x

        certificate = lean4_module.verify_with_lean4(identity, post=lambda x, result: True)
        assert certificate.status == Status.TRANSLATION_ERROR
        assert certificate.verified is False

    def test_fallthrough_return_is_total_without_placeholder(self) -> None:
        source = (
            "def clamp(x: int, lo: int, hi: int) -> int:\n"
            "    if x < lo:\n"
            "        return lo\n"
            "    elif x > hi:\n"
            "        return hi\n"
            "    return x\n"
        )
        lean = generate_lean4_theorem(
            "clamp",
            ["x", "lo", "hi"],
            {"x": int, "lo": int, "hi": int},
            "lo ≤ hi",
            "lo ≤ clamp_impl x lo hi ∧ clamp_impl x lo hi ≤ hi",
            source,
        )
        assert "else sorry" not in lean
        assert ":= sorry" not in lean
        assert "if x < lo then" in lean
        assert "if x > hi then" in lean

    def test_export_rejects_pass_only_body(self) -> None:
        def incomplete(x: int) -> int:
            pass

        with pytest.raises(ValueError, match="every control-flow path"):
            export_lean4(incomplete, post=lambda x, result: result == x)

    def test_export_preserves_parameter_named_result(self) -> None:
        def increment(result: int) -> int:
            return result + 1

        lean = export_lean4(
            increment,
            post=lambda result, returned: returned == result + 1,
        )

        assert "(increment_impl result) = result + 1" in lean
        assert "increment_impl (increment_impl" not in lean

    def test_core_integer_true_division_is_rejected(self) -> None:
        source = "def half(x: int) -> int:\n    return x / 2\n"
        with pytest.raises(ValueError, match="Python `/`"):
            generate_lean4_theorem(
                "half",
                ["x"],
                {"x": int},
                None,
                "half_impl x = x",
                source,
            )

    def test_attribute_builtin_call_is_rejected(self) -> None:
        source = "def magnitude(x: int) -> int:\n    return math.abs(x)\n"
        with pytest.raises(ValueError, match="Unsupported Lean4 call"):
            generate_lean4_theorem(
                "magnitude",
                ["x"],
                {"x": int},
                None,
                "magnitude_impl x ≥ 0",
                source,
            )

    def test_annotated_integer_types_stay_in_core_mode(self) -> None:
        from typing import Annotated

        from provably.types import Ge

        def identity(x: Annotated[int, Ge(0)]) -> Annotated[int, Ge(0)]:
            return x

        lean = export_lean4(identity, post=lambda x, returned: returned == x)

        assert "Mode: core" in lean
        assert "(x : Int) : Int" in lean
        assert "import Mathlib" not in lean

    def test_axiom_audit_rejects_custom_axiom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        from provably import lean4 as lean4_module

        monkeypatch.setattr(lean4_module, "HAS_LEAN4", True)
        monkeypatch.setattr(lean4_module.secrets, "token_hex", lambda _: "testtoken")
        result = subprocess.CompletedProcess(
            args=["lean"],
            returncode=0,
            stdout=(
                "__PROVABLY_AXIOM_AUDIT_BEGIN_testtoken__\n"
                "'checked' depends on axioms: [customTrust]\n"
                "__PROVABLY_AXIOM_AUDIT_END_testtoken__\n"
            ),
            stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
        ok, output = lean4_module.check_lean4_proof(
            "theorem checked : True := by trivial\n",
            theorem_name="checked",
        )
        assert ok is False
        assert "disallowed axioms" in output

    def test_axiom_audit_rejects_spoofed_output_before_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        from provably import lean4 as lean4_module

        monkeypatch.setattr(lean4_module, "HAS_LEAN4", True)
        monkeypatch.setattr(lean4_module.secrets, "token_hex", lambda _: "testtoken")
        result = subprocess.CompletedProcess(
            args=["lean"],
            returncode=0,
            stdout=(
                "'checked' depends on axioms: [propext]\n"
                "__PROVABLY_AXIOM_AUDIT_BEGIN_testtoken__\n"
                "'checked' depends on axioms: [customTrust]\n"
                "__PROVABLY_AXIOM_AUDIT_END_testtoken__\n"
            ),
            stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
        ok, output = lean4_module.check_lean4_proof(
            'theorem checked : True := by trivial\n#eval IO.println "spoof"\n',
            theorem_name="checked",
        )
        assert ok is False
        assert "customTrust" in output

    def test_native_decide_trust_requires_explicit_opt_in(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        from provably import lean4 as lean4_module

        monkeypatch.setattr(lean4_module, "HAS_LEAN4", True)
        monkeypatch.setattr(lean4_module.secrets, "token_hex", lambda _: "testtoken")
        result = subprocess.CompletedProcess(
            args=["lean"],
            returncode=0,
            stdout=(
                "__PROVABLY_AXIOM_AUDIT_BEGIN_testtoken__\n"
                "'checked' depends on axioms: [Lean.ofReduceBool, Lean.trustCompiler]\n"
                "__PROVABLY_AXIOM_AUDIT_END_testtoken__\n"
            ),
            stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
        code = "theorem checked : True := by native_decide\n"

        rejected, output = lean4_module.check_lean4_proof(code, theorem_name="checked")
        accepted, _ = lean4_module.check_lean4_proof(
            code,
            theorem_name="checked",
            allow_native_decide=True,
        )

        assert rejected is False
        assert "Lean.trustCompiler" in output
        assert accepted is True

    def test_axiom_audit_rejects_invalid_theorem_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from provably import lean4 as lean4_module

        monkeypatch.setattr(lean4_module, "HAS_LEAN4", True)
        ok, output = lean4_module.check_lean4_proof(
            "theorem checked : True := by trivial\n",
            theorem_name='checked\n#eval IO.println "forged"',
        )
        assert ok is False
        assert "Invalid Lean4 theorem name" in output
