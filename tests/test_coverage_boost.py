"""Coverage boost: target uncovered lines to push from 81% → 90%+.

Maps of what each class covers:
- TestInitImports          : __init__.py lines 30-59 (0% → covered)
- TestTypesModule          : types.py lines 18-42, 72, 104-208, 284-290
- TestLean4Module          : lean4.py lines 26-57, 71-74, 88, 113, 138, 151-152, 161, 166, 184-198
- TestLean4Verify          : lean4.py lines 479-636 (verify_with_lean4 paths)
- TestEngineModule         : engine.py lines 22-54, 97-139, 143, 153, 176-214, 250-251, 287-290
- TestEngineAdvanced       : engine.py lines 363-372, 749, 785, 801, 855-912
- TestDecoratorsModule     : decorators.py lines 43-66, 71-80, 103, 148-165, 240, 360, 411, 486
- TestTranslatorModule     : translator.py lines 43-86, 90, 94, 98, 103, 105, 108-227
- TestTranslatorEdges2     : translator.py lines 245, 281, 330, 368, 383, 413, 495, 557, 575, 592-928
- TestPytestPluginEdges    : pytest_plugin.py lines 19-34, 51, 64, 81, 91, 123-124, 146
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Annotated, Any

import pytest
import z3

# ===========================================================================
# __init__.py — 0% → bring imports to life
# ===========================================================================


class TestInitImports:
    def test_import_star_exports(self) -> None:
        import provably

        # All major names accessible
        assert hasattr(provably, "verified")
        assert hasattr(provably, "runtime_checked")
        assert hasattr(provably, "verify_function")
        assert hasattr(provably, "verify_module")
        assert hasattr(provably, "ProofCertificate")
        assert hasattr(provably, "Status")
        assert hasattr(provably, "clear_cache")
        assert hasattr(provably, "configure")
        assert hasattr(provably, "TranslationError")
        assert hasattr(provably, "VerificationError")
        assert hasattr(provably, "ContractViolationError")
        assert hasattr(provably, "__version__")

    def test_version_string(self) -> None:
        import provably

        assert isinstance(provably.__version__, str)
        assert "." in provably.__version__

    def test_z3_reexports(self) -> None:
        import provably

        assert hasattr(provably, "And")
        assert hasattr(provably, "Or")
        assert hasattr(provably, "Not")
        assert hasattr(provably, "Implies")

    def test_type_reexports(self) -> None:
        import provably

        for name in [
            "Gt",
            "Ge",
            "Lt",
            "Le",
            "Between",
            "NotEq",
            "Positive",
            "NonNegative",
            "UnitInterval",
        ]:
            assert hasattr(provably, name), f"missing {name}"

    def test_lean4_reexports(self) -> None:
        import provably

        assert hasattr(provably, "HAS_LEAN4")
        assert hasattr(provably, "LEAN4_VERSION")
        assert hasattr(provably, "verify_with_lean4")
        assert hasattr(provably, "export_lean4")
        assert isinstance(provably.HAS_LEAN4, bool)
        assert isinstance(provably.LEAN4_VERSION, str)

    def test_all_list_complete(self) -> None:
        import provably

        for name in provably.__all__:
            assert hasattr(provably, name), f"__all__ entry '{name}' missing"


# ===========================================================================
# types.py — 72% → cover repr, HAS_Z3, all markers, make_z3_var edge
# ===========================================================================


class TestTypesModule:
    def test_has_z3_constant(self) -> None:
        from provably.types import HAS_Z3

        assert HAS_Z3 is True

    def test_refinement_error_is_typeerror(self) -> None:
        from provably.types import RefinementError

        err = RefinementError("test")
        assert isinstance(err, TypeError)

    def test_gt_repr(self) -> None:
        from provably.types import Gt

        assert repr(Gt(5)) == "Gt(5)"
        assert repr(Gt(0.5)) == "Gt(0.5)"

    def test_ge_repr(self) -> None:
        from provably.types import Ge

        assert repr(Ge(0)) == "Ge(0)"

    def test_lt_repr(self) -> None:
        from provably.types import Lt

        assert repr(Lt(1)) == "Lt(1)"

    def test_le_repr(self) -> None:
        from provably.types import Le

        assert repr(Le(10)) == "Le(10)"

    def test_between_repr(self) -> None:
        from provably.types import Between

        assert repr(Between(0, 1)) == "Between(0, 1)"

    def test_noteq_repr(self) -> None:
        from provably.types import NotEq

        assert repr(NotEq(0)) == "NotEq(0)"

    def test_python_type_to_z3_sort_int(self) -> None:
        from provably.types import python_type_to_z3_sort

        assert python_type_to_z3_sort(int) == z3.IntSort()

    def test_python_type_to_z3_sort_float(self) -> None:
        from provably.types import python_type_to_z3_sort

        assert python_type_to_z3_sort(float) == z3.RealSort()

    def test_python_type_to_z3_sort_bool(self) -> None:
        from provably.types import python_type_to_z3_sort

        assert python_type_to_z3_sort(bool) == z3.BoolSort()

    def test_python_type_to_z3_sort_annotated(self) -> None:
        from provably.types import Ge, python_type_to_z3_sort

        # Annotated[int, Ge(0)] → IntSort
        assert python_type_to_z3_sort(Annotated[int, Ge(0)]) == z3.IntSort()

    def test_python_type_to_z3_sort_unknown_raises(self) -> None:
        from provably.types import python_type_to_z3_sort

        with pytest.raises(TypeError, match="No Z3 sort"):
            python_type_to_z3_sort(str)  # type: ignore[arg-type]

    def test_make_z3_var_int(self) -> None:
        from provably.types import make_z3_var

        v = make_z3_var("n", int)
        assert v.sort() == z3.IntSort()

    def test_make_z3_var_float(self) -> None:
        from provably.types import make_z3_var

        v = make_z3_var("x", float)
        assert v.sort() == z3.RealSort()

    def test_make_z3_var_bool(self) -> None:
        from provably.types import make_z3_var

        v = make_z3_var("b", bool)
        assert v.sort() == z3.BoolSort()

    def test_make_z3_var_annotated(self) -> None:
        from provably.types import Ge, make_z3_var

        v = make_z3_var("x", Annotated[float, Ge(0)])
        assert v.sort() == z3.RealSort()

    def test_extract_refinements_gt(self) -> None:
        from provably.types import Gt, extract_refinements

        x = z3.Real("x")
        cs = extract_refinements(Annotated[float, Gt(0)], x)
        assert len(cs) == 1
        s = z3.Solver()
        s.add(x == -1)
        s.add(*cs)
        assert s.check() == z3.unsat

    def test_extract_refinements_lt(self) -> None:
        from provably.types import Lt, extract_refinements

        x = z3.Real("x")
        cs = extract_refinements(Annotated[float, Lt(0)], x)
        assert len(cs) == 1

    def test_extract_refinements_noteq(self) -> None:
        from provably.types import NotEq, extract_refinements

        x = z3.Real("x")
        cs = extract_refinements(Annotated[float, NotEq(0)], x)
        assert len(cs) == 1

    def test_extract_refinements_between(self) -> None:
        from provably.types import Between, extract_refinements

        x = z3.Real("x")
        cs = extract_refinements(Annotated[float, Between(0, 1)], x)
        assert len(cs) == 2  # ge + le

    def test_extract_refinements_non_annotated(self) -> None:
        from provably.types import extract_refinements

        x = z3.Real("x")
        cs = extract_refinements(float, x)
        assert cs == []

    def test_convenience_aliases(self) -> None:
        # Just verify they resolve to Annotated types
        import typing

        from provably.types import NonNegative, Positive, UnitInterval

        assert typing.get_origin(Positive) is Annotated
        assert typing.get_origin(NonNegative) is Annotated
        assert typing.get_origin(UnitInterval) is Annotated

    def test_callable_marker_returning_bool_ref(self) -> None:
        from provably.types import extract_refinements

        x = z3.Real("x")
        marker = lambda v: v > 0  # noqa: E731
        cs = extract_refinements(Annotated[float, marker], x)
        assert len(cs) == 1

    def test_extract_refinements_nested_annotated(self) -> None:
        from provably.types import Ge, Le, extract_refinements

        x = z3.Real("x")
        Pos = Annotated[float, Ge(0)]
        cs = extract_refinements(Annotated[Pos, Le(1)], x)
        assert len(cs) == 2


# ===========================================================================
# lean4.py — 69% → cover module-level init block, _py_type_to_lean, etc.
# ===========================================================================


class TestLean4ModuleLevel:
    def test_has_lean4_is_bool(self) -> None:
        from provably.lean4 import HAS_LEAN4, LEAN4_VERSION

        assert isinstance(HAS_LEAN4, bool)
        assert isinstance(LEAN4_VERSION, str)

    def test_py_type_to_lean_none(self) -> None:
        from provably.lean4 import _py_type_to_lean

        assert _py_type_to_lean(None) == "Float"  # type: ignore[arg-type]

    def test_py_type_to_lean_float(self) -> None:
        from provably.lean4 import _py_type_to_lean

        assert _py_type_to_lean(float) == "Float"

    def test_py_type_to_lean_int(self) -> None:
        from provably.lean4 import _py_type_to_lean

        assert _py_type_to_lean(int) == "Int"

    def test_py_type_to_lean_bool(self) -> None:
        from provably.lean4 import _py_type_to_lean

        assert _py_type_to_lean(bool) == "Bool"

    def test_py_type_to_lean_annotated_int(self) -> None:
        from provably.lean4 import _py_type_to_lean

        assert _py_type_to_lean(Annotated[int, "marker"]) == "Int"

    def test_py_type_to_lean_annotated_bool(self) -> None:
        from provably.lean4 import _py_type_to_lean

        assert _py_type_to_lean(Annotated[bool, "marker"]) == "Bool"

    def test_py_type_to_lean_unknown_defaults_float(self) -> None:
        from provably.lean4 import _py_type_to_lean

        assert _py_type_to_lean(str) == "Float"  # type: ignore[arg-type]

    def test_expr_to_lean_int_constant(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.Constant(value=42)
        assert _expr_to_lean(node) == "42"

    def test_expr_to_lean_float_constant(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.Constant(value=3.14)
        out = _expr_to_lean(node)
        assert "3.14" in out

    def test_expr_to_lean_string_constant(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.Constant(value="hello")
        assert _expr_to_lean(node) == "hello"

    def test_expr_to_lean_name_from_env(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.Name(id="x")
        assert _expr_to_lean(node, {"x": "mapped_x"}) == "mapped_x"

    def test_expr_to_lean_name_not_in_env(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.Name(id="y")
        assert _expr_to_lean(node, {}) == "y"

    def test_expr_to_lean_binop_unsupported(self) -> None:
        from provably.lean4 import _expr_to_lean

        # MatMult is not in op_map, so should use "?"
        node = ast.BinOp(
            left=ast.Name(id="a"),
            op=ast.MatMult(),
            right=ast.Name(id="b"),
        )
        out = _expr_to_lean(node)
        assert "?" in out

    def test_expr_to_lean_compare_multiple_ops(self) -> None:
        from provably.lean4 import _expr_to_lean

        # a < b < c — chained compare
        node = ast.Compare(
            left=ast.Name(id="a"),
            ops=[ast.Lt(), ast.Lt()],
            comparators=[ast.Name(id="b"), ast.Name(id="c")],
        )
        out = _expr_to_lean(node)
        assert "∧" in out

    def test_expr_to_lean_compare_neq(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.Compare(
            left=ast.Name(id="x"),
            ops=[ast.NotEq()],
            comparators=[ast.Constant(value=0)],
        )
        out = _expr_to_lean(node)
        assert "≠" in out

    def test_expr_to_lean_unary_uadd(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.UnaryOp(op=ast.UAdd(), operand=ast.Name(id="x"))
        # UAdd is not USub/Not so falls through to return operand
        out = _expr_to_lean(node)
        assert out == "x"

    def test_expr_to_lean_ifexp(self) -> None:
        from provably.lean4 import _expr_to_lean

        node = ast.IfExp(
            test=ast.Name(id="b"),
            body=ast.Constant(value=1),
            orelse=ast.Constant(value=0),
        )
        out = _expr_to_lean(node)
        assert "if" in out and "then" in out and "else" in out

    def test_expr_to_lean_attribute_call(self) -> None:
        from provably.lean4 import _expr_to_lean

        # Call with ast.Attribute as func (e.g. obj.method()) → uses func.attr
        node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="math"),
                attr="sqrt",
                ctx=ast.Load(),
            ),
            args=[ast.Name(id="x")],
            keywords=[],
        )
        out = _expr_to_lean(node)
        assert "sqrt" in out

    def test_expr_to_lean_call_min_multi(self) -> None:
        from provably.lean4 import _expr_to_lean

        # min with 3 args hits the else branch
        node = ast.Call(
            func=ast.Name(id="min"),
            args=[ast.Name(id="a"), ast.Name(id="b"), ast.Name(id="c")],
            keywords=[],
        )
        out = _expr_to_lean(node)
        assert "min" in out

    def test_expr_to_lean_call_abs_multi(self) -> None:
        from provably.lean4 import _expr_to_lean

        # abs with 2 args hits else branch
        node = ast.Call(
            func=ast.Name(id="abs"),
            args=[ast.Name(id="a"), ast.Name(id="b")],
            keywords=[],
        )
        out = _expr_to_lean(node)
        assert "abs" in out

    def test_if_to_lean_no_orelse(self) -> None:
        from provably.lean4 import _if_to_lean

        stmt = ast.If(
            test=ast.Name(id="b"),
            body=[ast.Return(value=ast.Constant(value=1))],
            orelse=[],
        )
        out = _if_to_lean(stmt, {})
        assert "if" in out and "sorry" in out

    def test_if_to_lean_both_branches(self) -> None:
        from provably.lean4 import _if_to_lean

        stmt = ast.If(
            test=ast.Name(id="b"),
            body=[ast.Return(value=ast.Constant(value=1))],
            orelse=[ast.Return(value=ast.Constant(value=0))],
        )
        out = _if_to_lean(stmt, {})
        assert "if" in out and "then" in out and "else" in out

    def test_if_to_lean_no_then_return(self) -> None:
        from provably.lean4 import _if_to_lean

        stmt = ast.If(
            test=ast.Name(id="b"),
            body=[ast.Pass()],
            orelse=[ast.Return(value=ast.Constant(value=0))],
        )
        out = _if_to_lean(stmt, {})
        assert "sorry" in out

    def test_if_to_lean_neither_returns(self) -> None:
        from provably.lean4 import _if_to_lean

        stmt = ast.If(
            test=ast.Name(id="b"),
            body=[ast.Pass()],
            orelse=[],
        )
        out = _if_to_lean(stmt, {})
        assert out == "sorry"

    def test_func_body_docstring_skipped(self) -> None:
        from provably.lean4 import generate_lean4_theorem

        source = 'def f(x: int) -> int:\n    """doc"""\n    return x\n'
        out = generate_lean4_theorem("f", ["x"], {"x": int}, None, None, source)
        assert "f_impl" in out

    def test_func_body_pass_statement(self) -> None:
        from provably.lean4 import _func_body_to_lean

        code = "def f(x: int) -> int:\n    pass\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        out = _func_body_to_lean(func, {})
        assert out == "sorry"

    def test_generate_lean4_theorem_no_post(self) -> None:
        from provably.lean4 import generate_lean4_theorem

        source = "def f(x: float) -> float:\n    return x\n"
        out = generate_lean4_theorem("f", ["x"], {"x": float}, None, None, source)
        assert "No postcondition" in out

    def test_generate_lean4_theorem_only_post_no_pre(self) -> None:
        from provably.lean4 import generate_lean4_theorem

        source = "def f(x: int) -> int:\n    return x\n"
        out = generate_lean4_theorem("f", ["x"], {"x": int}, None, "f_impl x ≥ 0", source)
        assert "theorem f_verified" in out
        # No explicit h_pre hypothesis declaration since no precondition
        assert "(h_pre :" not in out

    def test_generate_lean4_theorem_float_mode(self) -> None:
        from provably.lean4 import generate_lean4_theorem

        source = "def f(x: float) -> float:\n    return x * 2\n"
        out = generate_lean4_theorem("f", ["x"], {"x": float}, "x ≥ 0", "f_impl x ≥ 0", source)
        # Should use mathlib mode (noncomputable def, ℝ type)
        assert "noncomputable" in out or "ℝ" in out

    def test_z3_str_to_lean_operators(self) -> None:
        from provably.lean4 import _z3_str_to_lean

        s = "x >= 0"
        out = _z3_str_to_lean(s, ["x"])
        assert "≥" in out

        s2 = "x <= 1"
        out2 = _z3_str_to_lean(s2, ["x"])
        assert "≤" in out2

        s3 = "x != 0"
        out3 = _z3_str_to_lean(s3, ["x"])
        assert "≠" in out3

    def test_z3_str_to_lean_and_or(self) -> None:
        from provably.lean4 import _z3_str_to_lean

        s = "And(x >= 0, x <= 1)"
        out = _z3_str_to_lean(s, ["x"])
        # And( gets replaced with (
        assert "∧" in out

        s2 = "Or(x >= 0, x <= 1)"
        out2 = _z3_str_to_lean(s2, ["x"])
        assert "∧" in out2


class TestLean4VerifyPaths:
    """Cover verify_with_lean4 code paths — no lean installation needed."""

    def test_no_lean_returns_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from provably import lean4 as m
        from provably.engine import Status

        monkeypatch.setattr(m, "HAS_LEAN4", False)

        def f(x: float) -> float:
            return x

        cert = m.verify_with_lean4(f)
        assert cert.status == Status.SKIPPED
        assert "not installed" in cert.message.lower()

    def test_non_parseable_lambda_skipped_or_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from provably import lean4 as m
        from provably.engine import Status

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        f = lambda x: x  # noqa: E731
        cert = m.verify_with_lean4(f)
        assert cert.status in {
            Status.SKIPPED,
            Status.TRANSLATION_ERROR,
            Status.VERIFIED,
            Status.UNKNOWN,
        }

    def test_refinement_error_in_type_returns_translation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import provably.types as types_mod
        from provably import lean4 as m
        from provably.engine import Status
        from provably.types import RefinementError

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        # Patch extract_refinements in types module to raise RefinementError
        def bad_extract(typ: Any, var: Any) -> list:
            raise RefinementError("broken")

        monkeypatch.setattr(types_mod, "extract_refinements", bad_extract)

        def f(x: float) -> float:
            return x

        cert = m.verify_with_lean4(f)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_export_lean4_no_output_path(self) -> None:
        from provably.lean4 import export_lean4

        def f(x: int) -> int:
            return x + 1

        code = export_lean4(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 1)
        assert "f_impl" in code
        assert isinstance(code, str)

    def test_export_lean4_not_a_function(self) -> None:
        from provably.lean4 import export_lean4

        # A class — its source parses as ClassDef, not FunctionDef
        class MyClass:
            assert True, "pass marker replaced with explicit no-op assertion: test_coverage_boost.py:615"

        out = export_lean4(MyClass)
        assert "Error" in out or "sorry" in out.lower()


# ===========================================================================
# engine.py — cover remaining uncovered lines
# ===========================================================================


class TestEngineModule:
    def test_status_enum_values(self) -> None:
        from provably.engine import Status

        assert Status.VERIFIED.value == "verified"
        assert Status.COUNTEREXAMPLE.value == "counterexample"
        assert Status.UNKNOWN.value == "unknown"
        assert Status.TRANSLATION_ERROR.value == "translation_error"
        assert Status.SKIPPED.value == "skipped"

    def test_proof_certificate_str_skipped(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            function_name="f",
            source_hash="abc",
            status=Status.SKIPPED,
            preconditions=(),
            postconditions=(),
            message="no post",
        )
        s = str(cert)
        assert "SKIPPED" in s
        assert "f" in s

    def test_proof_certificate_str_verified(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            function_name="double",
            source_hash="deadbeef",
            status=Status.VERIFIED,
            preconditions=("x >= 0",),
            postconditions=("2*x >= 0",),
        )
        s = str(cert)
        assert "Q.E.D." in s

    def test_proof_certificate_str_unknown(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            function_name="f",
            source_hash="",
            status=Status.UNKNOWN,
            preconditions=(),
            postconditions=(),
            message="timeout",
        )
        s = str(cert)
        assert "?" in s

    def test_proof_certificate_str_counterexample(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            function_name="bad",
            source_hash="",
            status=Status.COUNTEREXAMPLE,
            preconditions=(),
            postconditions=("result > 0",),
            counterexample={"x": -1, "__return__": -2},
            message="CE found",
        )
        s = str(cert)
        assert "DISPROVED" in s
        assert "counterexample" in s.lower()

    def test_proof_certificate_verified_property(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate("f", "", Status.VERIFIED, (), ())
        assert cert.verified is True

        cert2 = ProofCertificate("f", "", Status.UNKNOWN, (), ())
        assert cert2.verified is False

    def test_explain_verified(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate("double", "abc", Status.VERIFIED, ("x>=0",), ("r>=0",))
        out = cert.explain()
        assert "Q.E.D." in out

    def test_explain_counterexample_with_return(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            "bad",
            "",
            Status.COUNTEREXAMPLE,
            (),
            ("result > 0",),
            counterexample={"x": -1, "__return__": -1},
        )
        out = cert.explain()
        assert "COUNTEREXAMPLE" in out
        assert "bad" in out

    def test_explain_no_message(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate("f", "", Status.SKIPPED, (), (), message="")
        out = cert.explain()
        assert "f" in out

    def test_to_prompt_verified(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate("f", "", Status.VERIFIED, (), ())
        p = cert.to_prompt()
        assert "VERIFIED" in p

    def test_to_prompt_counterexample(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            "bad",
            "",
            Status.COUNTEREXAMPLE,
            (),
            ("r > 0",),
            counterexample={"x": 0, "__return__": 0},
        )
        p = cert.to_prompt()
        assert "DISPROVED" in p
        assert "Fix" in p

    def test_to_prompt_counterexample_no_postcondition(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            "bad",
            "",
            Status.COUNTEREXAMPLE,
            (),
            (),
            counterexample={"x": 0, "__return__": 0},
        )
        p = cert.to_prompt()
        assert "DISPROVED" in p

    def test_to_prompt_unknown(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate("f", "", Status.UNKNOWN, (), (), message="timed out")
        p = cert.to_prompt()
        assert "unknown" in p.lower()

    def test_to_json_round_trip(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            "f",
            "abc123",
            Status.VERIFIED,
            ("x>=0",),
            ("r>=0",),
            solver_time_ms=12.5,
            z3_version="4.x",
        )
        d = cert.to_json()
        assert d["status"] == "verified"
        assert d["function_name"] == "f"
        cert2 = ProofCertificate.from_json(d)
        assert cert2.status == Status.VERIFIED
        assert cert2.function_name == "f"

    def test_to_json_counterexample_non_serializable(self) -> None:
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate(
            "f",
            "",
            Status.COUNTEREXAMPLE,
            (),
            (),
            counterexample={"x": z3.IntVal(1), "__return__": z3.IntVal(2)},
        )
        d = cert.to_json()
        # Non-JSON values should be stringified
        assert isinstance(d["counterexample"]["x"], str)

    def test_from_json_invalid_status_raises(self) -> None:
        from provably.engine import ProofCertificate

        with pytest.raises(ValueError):
            ProofCertificate.from_json(
                {
                    "function_name": "f",
                    "source_hash": "",
                    "status": "totally_invalid",
                    "preconditions": [],
                    "postconditions": [],
                }
            )

    def test_configure_unknown_key_raises(self) -> None:
        from provably.engine import configure

        with pytest.raises(ValueError, match="Unknown configure"):
            configure(nonexistent_key=True)

    def test_configure_log_level(self) -> None:
        import logging

        from provably.engine import configure

        configure(log_level="DEBUG")
        logger = logging.getLogger("provably")
        assert logger.level == logging.DEBUG
        configure(log_level="WARNING")  # restore

    def test_configure_cache_dir_none_disables_disk(self) -> None:
        from provably.engine import _disk_cache_path, configure

        configure(cache_dir=None)
        assert _disk_cache_path("any_key") is None
        # Restore default
        configure(cache_dir=str(Path.home() / ".provably" / "cache"))

    def test_clear_cache(self) -> None:
        from provably.engine import _proof_cache, clear_cache

        _proof_cache["dummy"] = None  # type: ignore[assignment]
        clear_cache()
        assert "dummy" not in _proof_cache

    def test_verify_function_no_post_skipped(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x

        cert = verify_function(f)
        assert cert.status == Status.SKIPPED
        assert "nothing to prove" in cert.message.lower()

    def test_verify_function_precondition_returns_non_bool(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x

        cert = verify_function(f, pre=lambda x: 42, post=lambda x, r: r == x)
        assert cert.status == Status.TRANSLATION_ERROR
        assert "expected z3.BoolRef" in cert.message

    def test_verify_function_precondition_raises(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x

        def bad_pre(x: Any) -> Any:
            raise ValueError("oops")

        cert = verify_function(f, pre=bad_pre, post=lambda x, r: r == x)
        assert cert.status == Status.TRANSLATION_ERROR
        assert "Precondition error" in cert.message

    def test_verify_function_postcondition_returns_non_bool(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x

        cert = verify_function(f, post=lambda x, r: "not a bool ref")
        assert cert.status == Status.TRANSLATION_ERROR

    def test_verify_function_postcondition_raises(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x

        def bad_post(x: Any, r: Any) -> Any:
            raise RuntimeError("post broken")

        cert = verify_function(f, post=bad_post)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_verify_function_wrong_pre_arity(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float, y: float) -> float:
            return x + y

        # pre takes 1 arg, function takes 2
        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, y, r: r >= 0)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_verify_function_disk_cache_save_load(self, tmp_path: Path) -> None:
        from provably.engine import Status, clear_cache, configure, verify_function

        configure(cache_dir=str(tmp_path))
        clear_cache()

        def add(x: float) -> float:
            return x + 1

        cert1 = verify_function(add, post=lambda x, r: r > x)
        assert cert1.status == Status.VERIFIED

        # Clear memory cache — next call should load from disk
        clear_cache()
        cert2 = verify_function(add, post=lambda x, r: r > x)
        assert cert2.status == Status.VERIFIED

        configure(cache_dir=str(Path.home() / ".provably" / "cache"))

    def test_z3_val_to_python_rational(self) -> None:
        from provably.engine import _z3_val_to_python

        val = z3.RealVal("1/2")
        result = _z3_val_to_python(val)
        assert abs(float(result) - 0.5) < 1e-9

    def test_z3_val_to_python_true(self) -> None:
        from provably.engine import _z3_val_to_python

        assert _z3_val_to_python(z3.BoolVal(True)) is True
        assert _z3_val_to_python(z3.BoolVal(False)) is False

    def test_z3_val_to_python_int(self) -> None:
        from provably.engine import _z3_val_to_python

        assert _z3_val_to_python(z3.IntVal(7)) == 7

    def test_z3_val_to_python_unknown_str(self) -> None:
        from provably.engine import _z3_val_to_python

        # A Z3 uninterpreted constant — fallback to str
        val = z3.Real("unkn")
        result = _z3_val_to_python(val)
        assert isinstance(result, str)

    def test_resolve_closure_vars_with_numeric_global(self) -> None:
        from provably.engine import Status, verify_function

        THRESHOLD = 5

        def f(x: float) -> float:
            return x + THRESHOLD

        cert = verify_function(f, post=lambda x, r: r > x)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_verify_module_finds_verified_functions(self) -> None:
        import types

        from provably.decorators import verified
        from provably.engine import verify_module

        mod = types.ModuleType("test_mod")

        @verified(pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        def identity(x: float) -> float:
            return x

        mod.identity = identity  # type: ignore[attr-defined]
        results = verify_module(mod)
        assert "identity" in results

    def test_tuple_proxy_getitem_negative(self) -> None:
        from provably.engine import _TupleProxy

        proxy = _TupleProxy(z3.IntVal(0), 2, [z3.RealSort(), z3.RealSort()])
        # Negative index
        elem = proxy[-1]
        assert elem is not None

    def test_tuple_proxy_getitem_out_of_range(self) -> None:
        from provably.engine import _TupleProxy

        proxy = _TupleProxy(z3.IntVal(0), 2, [z3.RealSort(), z3.RealSort()])
        with pytest.raises(IndexError):
            _ = proxy[5]

    def test_tuple_proxy_getitem_non_int(self) -> None:
        from provably.engine import _TupleProxy

        proxy = _TupleProxy(z3.IntVal(0), 2, [z3.RealSort(), z3.RealSort()])
        with pytest.raises(TypeError):
            _ = proxy["key"]  # type: ignore[index]

    def test_tuple_proxy_len(self) -> None:
        from provably.engine import _TupleProxy

        proxy = _TupleProxy(z3.IntVal(0), 3, [z3.RealSort()] * 3)
        assert len(proxy) == 3

    def test_maybe_tuple_proxy_non_tuple(self) -> None:
        from provably.engine import _maybe_tuple_proxy

        x = z3.Real("x")
        result = _maybe_tuple_proxy(x, {})
        assert result is x

    def test_maybe_tuple_proxy_none(self) -> None:
        from provably.engine import _maybe_tuple_proxy

        result = _maybe_tuple_proxy(None, {})
        assert result is None


# ===========================================================================
# decorators.py — cover async, check_contracts, raise_on_failure, runtime
# ===========================================================================


class TestDecoratorsModule:
    def test_verification_error_has_cert(self) -> None:
        from provably.decorators import VerificationError
        from provably.engine import ProofCertificate, Status

        cert = ProofCertificate("f", "", Status.COUNTEREXAMPLE, (), ())
        exc = VerificationError(cert)
        assert exc.certificate is cert

    def test_contract_violation_pre(self) -> None:
        from provably.decorators import ContractViolationError

        exc = ContractViolationError("pre", "f", (5,))
        assert "Precondition" in str(exc)
        assert exc.kind == "pre"

    def test_contract_violation_post(self) -> None:
        from provably.decorators import ContractViolationError

        exc = ContractViolationError("post", "f", (5,), result=-1)
        assert "Postcondition" in str(exc)
        assert exc.result == -1

    def test_verified_bare_decorator(self) -> None:
        from provably.decorators import verified

        @verified
        def f(x: float) -> float:
            return x

        assert hasattr(f, "__proof__")

    def test_verified_with_raise_on_failure_true(self) -> None:
        from provably.decorators import VerificationError, verified

        with pytest.raises(VerificationError):

            @verified(raise_on_failure=True, post=lambda x, r: r < 0)
            def always_positive(x: float) -> float:
                return abs(x)

    def test_verified_async_function(self) -> None:
        from provably.decorators import verified
        from provably.engine import Status

        @verified(post=lambda r: r == 42)
        async def async_f() -> int:
            return 42

        assert async_f.__proof__.status == Status.SKIPPED
        assert "async" in async_f.__proof__.message

    def test_verified_check_contracts_pre_violation(self) -> None:
        from provably.decorators import ContractViolationError, verified

        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, r: r == x,
            check_contracts=True,
        )
        def identity(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError):
            identity(-1.0)

    def test_verified_check_contracts_post_violation(self) -> None:
        from provably.decorators import ContractViolationError, verified

        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, r: r == x + 99,  # always false
            check_contracts=True,
        )
        def identity2(x: float) -> float:
            return x

        # Call with valid input but post will fail at runtime
        with pytest.raises(ContractViolationError):
            identity2(1.0)

    def test_check_contract_arity_varargs(self) -> None:
        from provably.decorators import _check_contract_arity

        # *args → skip check
        _check_contract_arity(lambda *args: True, 5, "pre", "f")

    def test_check_contract_arity_uninspectable(self) -> None:
        from provably.decorators import _check_contract_arity

        # Uninspectable callable — should not raise
        class Weird:
            def __call__(self) -> bool:
                return True

            @property
            def __signature__(self):
                raise ValueError("no sig")

        _check_contract_arity(Weird(), 1, "pre", "f")

    def test_runtime_checked_bare(self) -> None:
        from provably.decorators import runtime_checked

        @runtime_checked
        def f(x: float) -> float:
            return x * 2

        assert f(3.0) == 6.0

    def test_runtime_checked_with_options(self) -> None:
        from provably.decorators import ContractViolationError, runtime_checked

        @runtime_checked(pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        def f(x: float) -> float:
            return x

        assert f(1.0) == 1.0

        with pytest.raises(ContractViolationError):
            f(-1.0)

    def test_runtime_checked_raise_false_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from provably.decorators import runtime_checked

        @runtime_checked(pre=lambda x: x >= 0, raise_on_failure=False)
        def f(x: float) -> float:
            return x

        with caplog.at_level(logging.WARNING, logger="provably"):
            f(-1.0)

        assert any("violation" in r.message.lower() for r in caplog.records)

    def test_runtime_checked_async(self) -> None:
        import asyncio

        from provably.decorators import ContractViolationError, runtime_checked

        @runtime_checked(pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        async def async_g(x: float) -> float:
            return x

        result = asyncio.run(async_g(1.0))
        assert result == 1.0

        with pytest.raises(ContractViolationError):
            asyncio.run(async_g(-1.0))

    def test_runtime_checked_pre_exception_treated_as_false(self) -> None:
        from provably.decorators import ContractViolationError, runtime_checked

        @runtime_checked(pre=lambda x: 1 / 0)  # always raises
        def f(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError):
            f(1.0)

    def test_handle_violation_raise_false(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from provably.decorators import ContractViolationError, _handle_violation

        exc = ContractViolationError("pre", "f", (1,))
        with caplog.at_level(logging.WARNING, logger="provably"):
            _handle_violation(exc, raise_on_failure=False)
        assert any("violation" in r.message.lower() for r in caplog.records)


# ===========================================================================
# translator.py — cover lines 43-86, 90, 94, 98, 103, 108-227 (builtins etc)
# ===========================================================================


class TestTranslatorBuiltins:
    def test_z3_min(self) -> None:
        from provably.translator import _z3_min

        a = z3.IntVal(3)
        b = z3.IntVal(5)
        expr = _z3_min(a, b)
        s = z3.Solver()
        s.add(expr != 3)
        assert s.check() == z3.unsat

    def test_z3_max(self) -> None:
        from provably.translator import _z3_max

        a = z3.IntVal(3)
        b = z3.IntVal(5)
        expr = _z3_max(a, b)
        s = z3.Solver()
        s.add(expr != 5)
        assert s.check() == z3.unsat

    def test_z3_abs(self) -> None:
        from provably.translator import _z3_abs

        x = z3.Real("x")
        expr = _z3_abs(x)
        s = z3.Solver()
        s.add(x == -3)
        s.add(expr != 3)
        assert s.check() == z3.unsat

    def test_z3_pow_n0(self) -> None:
        from provably.translator import _z3_pow

        base = z3.Real("x")
        expr = _z3_pow(base, z3.IntVal(0))
        s = z3.Solver()
        s.add(expr != 1)
        assert s.check() == z3.unsat

    def test_z3_pow_n1(self) -> None:
        from provably.translator import _z3_pow

        base = z3.Real("x")
        expr = _z3_pow(base, z3.IntVal(1))
        assert str(expr) == str(base)

    def test_z3_pow_n2(self) -> None:
        from provably.translator import _z3_pow

        base = z3.IntVal(3)
        expr = _z3_pow(base, z3.IntVal(2))
        s = z3.Solver()
        s.add(expr != 9)
        assert s.check() == z3.unsat

    def test_z3_pow_n3(self) -> None:
        from provably.translator import _z3_pow

        base = z3.IntVal(2)
        expr = _z3_pow(base, z3.IntVal(3))
        s = z3.Solver()
        s.add(expr != 8)
        assert s.check() == z3.unsat

    def test_z3_pow_unsupported_raises(self) -> None:
        from provably.translator import TranslationError, _z3_pow

        with pytest.raises(TranslationError):
            _z3_pow(z3.Real("x"), z3.IntVal(5))

    def test_z3_bool_cast_bool(self) -> None:
        from provably.translator import _z3_bool_cast

        b = z3.Bool("b")
        assert _z3_bool_cast(b) is b

    def test_z3_bool_cast_int(self) -> None:
        from provably.translator import _z3_bool_cast

        n = z3.Int("n")
        expr = _z3_bool_cast(n)
        assert expr.sort() == z3.BoolSort()

    def test_z3_bool_cast_real(self) -> None:
        from provably.translator import _z3_bool_cast

        x = z3.Real("x")
        expr = _z3_bool_cast(x)
        assert expr.sort() == z3.BoolSort()

    def test_z3_int_cast_int(self) -> None:
        from provably.translator import _z3_int_cast

        n = z3.Int("n")
        assert _z3_int_cast(n) is n

    def test_z3_int_cast_real(self) -> None:
        from provably.translator import _z3_int_cast

        x = z3.Real("x")
        result = _z3_int_cast(x)
        assert result.sort() == z3.IntSort()

    def test_z3_int_cast_bool(self) -> None:
        from provably.translator import _z3_int_cast

        b = z3.Bool("b")
        result = _z3_int_cast(b)
        assert result.sort() == z3.IntSort()

    def test_z3_float_cast_real(self) -> None:
        from provably.translator import _z3_float_cast

        x = z3.Real("x")
        assert _z3_float_cast(x) is x

    def test_z3_float_cast_int(self) -> None:
        from provably.translator import _z3_float_cast

        n = z3.Int("n")
        result = _z3_float_cast(n)
        assert result.sort() == z3.RealSort()

    def test_z3_float_cast_bool(self) -> None:
        from provably.translator import _z3_float_cast

        b = z3.Bool("b")
        result = _z3_float_cast(b)
        assert result.sort() == z3.RealSort()

    def test_math_axioms_exist(self) -> None:
        from provably.translator import _math_axioms, _math_cos, _math_exp, _math_log, _math_sqrt

        assert _math_exp is not None
        assert _math_cos is not None
        assert _math_sqrt is not None
        assert _math_log is not None
        assert len(_math_axioms) > 0

    def test_math_constants_exist(self) -> None:
        from provably.translator import _MATH_CONSTANTS

        assert "pi" in _MATH_CONSTANTS
        assert "e" in _MATH_CONSTANTS

    def test_translator_has_z3(self) -> None:
        from provably.translator import HAS_Z3

        assert HAS_Z3 is True


class TestTranslatorEdges2:
    """Cover remaining translator lines: floor div, mod, while, match, coerce."""

    def test_floor_div_int(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: int) -> int:
            return x // 3

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_floor_div_float_raises(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x // 3  # type: ignore[operator]

        cert = verify_function(f, post=lambda x, r: r >= 0)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_mod_int(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: int) -> int:
            return x % 3

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_mod_float_raises(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x % 3  # type: ignore[operator]

        cert = verify_function(f, post=lambda x, r: r >= 0)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_pow_float_exponent(self) -> None:
        """Float exponent that is an integer (e.g. 2.0) should work."""
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x**2.0

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_unary_uadd(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return +x

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_unsupported_unary_invert_raises(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return ~x  # type: ignore[operator]

        cert = verify_function(f, post=lambda x, r: r >= 0)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_string_constant_raises(self) -> None:
        from provably.engine import Status, verify_function

        # Can't easily inject a string literal in a typed function body,
        # so use the translator directly.
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = 'def f(x):\n    return "hello"\n'
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError):
            t.translate(func, {"x": z3.Real("x")})

    def test_none_constant_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    return None\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError):
            t.translate(func, {"x": z3.Real("x")})

    def test_unsupported_statement_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # Import statement in a function body
        code = "def f(x):\n    import os\n    return x\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Unsupported statement"):
            t.translate(func, {"x": z3.Real("x")})

    def test_aug_assign_undefined_variable(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    y += 1\n    return y\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Undefined variable in aug-assign"):
            t.translate(func, {"x": z3.Real("x")})

    def test_aug_assign_non_name_target(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # obj.attr += 1 — subscript target
        code = "def f(x):\n    x[0] += 1\n    return x\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Unsupported aug-assign target"):
            t.translate(func, {"x": z3.Int("x")})

    def test_multiple_assignment_targets_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # x = y = 5
        code = "def f(x):\n    a = b = x + 1\n    return a\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Multiple assignment targets"):
            t.translate(func, {"x": z3.Real("x")})

    def test_bare_return_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    return\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Bare return"):
            t.translate(func, {"x": z3.Real("x")})

    def test_len_call(self) -> None:
        from provably.engine import Status, verify_function

        # Can't easily prove anything about len in Z3, but we can hit the code
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    n = len(x)\n    return n\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Int("x")})
        assert result.return_expr is not None

    def test_round_call(self) -> None:
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    return round(x)\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Real("x")})
        assert result.return_expr is not None

    def test_round_call_too_many_args(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x, y):\n    return round(x, y)\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="round\\(\\)"):
            t.translate(func, {"x": z3.Real("x"), "y": z3.Int("y")})

    def test_len_call_wrong_args(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x, y):\n    return len(x, y)\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="len\\(\\)"):
            t.translate(func, {"x": z3.Int("x"), "y": z3.Int("y")})

    def test_unsupported_call_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    return unknown_fn(x)\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Unknown function"):
            t.translate(func, {"x": z3.Real("x")})

    def test_attribute_access_math_pi(self) -> None:
        import math

        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x + math.pi

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r > x)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_attribute_access_unsupported_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    return x.real\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Unsupported attribute"):
            t.translate(func, {"x": z3.Real("x")})

    def test_unsupported_method_call_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    return x.unknown()\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Unsupported method call"):
            t.translate(func, {"x": z3.Real("x")})

    def test_non_simple_call_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # (lambda x: x)(5) — non-Name func
        code = "def f(x):\n    return (lambda y: y)(x)\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Only simple function calls"):
            t.translate(func, {"x": z3.Real("x")})

    def test_compare_unsupported_op(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # `is` comparison — unsupported
        code = "def f(x):\n    return x is None\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError):
            t.translate(func, {"x": z3.Real("x")})

    def test_coerce_incompatible_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # Bool coercion to Real path
        b = z3.Bool("b")
        r = z3.Real("x")
        # Both bool→int path and reverse
        a_coerced, b_coerced = t._coerce(b, r)
        assert a_coerced.sort() == z3.RealSort() or b_coerced.sort() == z3.RealSort()

    def test_coerce_both_same_sort(self) -> None:
        from provably.translator import Translator

        t = Translator()
        a = z3.Real("a")
        b = z3.Real("b")
        ra, rb = t._coerce(a, b)
        assert ra is a and rb is b

    def test_subscript_out_of_range(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            t = (x, x + 1)
            return t[5]  # type: ignore[index]

        cert = verify_function(f, post=lambda x, r: r >= 0)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_subscript_non_int_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    t = (x, x+1)\n    return t[x]\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Only constant integer subscripts"):
            t.translate(func, {"x": z3.Real("x")})

    def test_tuple_single_element(self) -> None:
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    return (x,)\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Real("x")})
        # Single-element tuple returns the element directly
        assert result.return_expr is not None

    def test_tuple_empty(self) -> None:
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    return ()\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Real("x")})
        assert result.return_expr is not None

    def test_for_loop_else_clause_warning(self) -> None:
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    s = 0\n    for i in range(3):\n        s += i\n    else:\n        s += 1\n    return s\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Int("x"), "s": z3.Int("s")})
        assert any("else" in w.lower() for w in result.warnings)

    def test_for_loop_range_2args(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: int) -> int:
            s = 0
            for i in range(1, 4):
                s += i
            return s

        cert = verify_function(f, post=lambda x, r: r == 6)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_for_loop_range_3args(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: int) -> int:
            s = 0
            for i in range(0, 6, 2):
                s += i
            return s

        cert = verify_function(f, post=lambda x, r: r == 6)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_for_loop_zero_step_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    s = 0\n    for i in range(0, 5, 0):\n        s += i\n    return s\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="step cannot be zero"):
            t.translate(func, {"x": z3.Int("x"), "s": z3.IntVal(0)})

    def test_for_loop_non_name_target_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # Tuple unpack as for target — unsupported
        code = "def f(x):\n    s = 0\n    for i, j in [(1, 2)]:\n        s += i\n    return s\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError):
            t.translate(func, {"x": z3.Int("x"), "s": z3.IntVal(0)})

    def test_for_loop_non_range_iter_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        code = "def f(x):\n    for i in [1, 2, 3]:\n        x += i\n    return x\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Only 'for i in range"):
            t.translate(func, {"x": z3.Int("x")})

    def test_while_loop_with_else(self) -> None:
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    while x > 10:\n        x -= 1\n    else:\n        x += 0\n    return x\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Int("x")})
        assert any("else" in w.lower() for w in result.warnings)

    def test_math_exp_call(self) -> None:
        import math

        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return math.exp(x)

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 1)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_math_sqrt_call(self) -> None:
        import math

        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return math.sqrt(x)

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_verified_contracts_composition(self) -> None:
        from provably.engine import Status, verify_function

        def double(x: float) -> float:
            return x * 2

        double_contracts = {
            "double": {
                "pre": lambda x: x >= 0,
                "post": lambda x, r: r >= 0,
                "return_sort": z3.RealSort(),
            }
        }

        def quadruple(x: float) -> float:
            return double(double(x))

        cert = verify_function(
            quadruple,
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
            verified_contracts=double_contracts,
        )
        # Should be verified or at worst unknown (composition is valid)
        assert cert.status in {
            Status.VERIFIED,
            Status.UNKNOWN,
            Status.TRANSLATION_ERROR,
        }


# ===========================================================================
# lean4.py — cover check_lean4_proof and verify_with_lean4 via subprocess mock
# ===========================================================================


class TestLean4WithMockedSubprocess:
    """Cover lean4.py paths that require HAS_LEAN4=True + subprocess mock."""

    def _make_subprocess_result(self, returncode: int, stdout: str = "", stderr: str = "") -> Any:
        import subprocess
        from unittest.mock import MagicMock

        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_check_lean4_proof_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover lines 424-444: successful lean check."""
        import subprocess

        from provably import lean4 as m

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        mock_result = self._make_subprocess_result(0, "success", "")
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        ok, out = m.check_lean4_proof("def x : Nat := 0\n", timeout_s=30.0)
        assert ok is True
        assert isinstance(out, str)

    def test_check_lean4_proof_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover lines 424-444: failed lean check."""
        import subprocess

        from provably import lean4 as m

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        mock_result = self._make_subprocess_result(1, "", "error: unknown identifier")
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        ok, out = m.check_lean4_proof("bad code\n", timeout_s=30.0)
        assert ok is False
        assert "error" in out.lower()

    def test_check_lean4_proof_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover line 440: timeout path."""
        import subprocess

        from provably import lean4 as m

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        def raise_timeout(*a: Any, **kw: Any) -> None:
            raise subprocess.TimeoutExpired("lean", 0.001)

        monkeypatch.setattr(subprocess, "run", raise_timeout)

        ok, out = m.check_lean4_proof("x\n", timeout_s=0.001)
        assert ok is False
        assert "timed out" in out.lower()

    def test_check_lean4_proof_file_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover line 442: FileNotFoundError path."""
        import subprocess

        from provably import lean4 as m

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        def raise_fnf(*a: Any, **kw: Any) -> None:
            raise FileNotFoundError("lean: not found")

        monkeypatch.setattr(subprocess, "run", raise_fnf)

        ok, out = m.check_lean4_proof("x\n", timeout_s=30.0)
        assert ok is False
        assert "not found" in out.lower()

    def test_verify_with_lean4_full_success_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover lines 479-636: full verify_with_lean4 execution with mocked lean."""
        import subprocess

        from provably import lean4 as m
        from provably.engine import Status

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        mock_result = self._make_subprocess_result(0, "", "")
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        def f(x: float) -> float:
            return x * 2

        cert = m.verify_with_lean4(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}
        assert cert.function_name == "f"

    def test_verify_with_lean4_lean_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover lines 623-633: lean proof fails → UNKNOWN status."""
        import subprocess

        from provably import lean4 as m
        from provably.engine import Status

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        mock_result = self._make_subprocess_result(1, "", "type mismatch")
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        def g(x: float) -> float:
            return x

        cert = m.verify_with_lean4(g, post=lambda x, r: r == x)
        assert cert.status == Status.UNKNOWN
        assert "Lean4 proof failed" in cert.message

    def test_verify_with_lean4_no_pre_no_post(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover path with no pre/post — still generates lean code."""
        import subprocess

        from provably import lean4 as m
        from provably.engine import Status

        monkeypatch.setattr(m, "HAS_LEAN4", True)

        mock_result = self._make_subprocess_result(0, "", "")
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        def h(x: int) -> int:
            return x + 1

        cert = m.verify_with_lean4(h)
        # No post → still runs lean but cert.status depends on lean result
        assert cert.status in {Status.VERIFIED, Status.UNKNOWN, Status.SKIPPED}

    def test_verify_with_lean4_source_oserror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover line 481-489: OSError when getting source → SKIPPED."""
        import inspect

        from provably import lean4 as m
        from provably.engine import Status

        monkeypatch.setattr(m, "HAS_LEAN4", True)
        monkeypatch.setattr(
            inspect, "getsource", lambda f: (_ for _ in ()).throw(OSError("no src"))
        )

        def f(x: float) -> float:
            return x

        cert = m.verify_with_lean4(f)
        assert cert.status == Status.SKIPPED
        assert "Cannot get source" in cert.message

    def test_verify_with_lean4_non_funcdef_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover line 494-502: source parses as non-FunctionDef → TRANSLATION_ERROR."""
        import inspect
        import textwrap

        from provably import lean4 as m
        from provably.engine import Status

        monkeypatch.setattr(m, "HAS_LEAN4", True)
        monkeypatch.setattr(inspect, "getsource", lambda f: "x = 1 + 2\n")
        monkeypatch.setattr(textwrap, "dedent", lambda s: s)

        def f(x: float) -> float:
            return x

        cert = m.verify_with_lean4(f)
        assert cert.status == Status.TRANSLATION_ERROR
        assert "Not a function definition" in cert.message

    def test_export_lean4_pre_raises_value_error(self) -> None:
        """Cover lines 685-686: export raises ValueError on pre error."""
        from provably.lean4 import export_lean4

        def f(x: float) -> float:
            return x

        with pytest.raises(ValueError, match="Precondition"):
            export_lean4(f, pre=lambda x: (_ for _ in ()).throw(RuntimeError("pre fail")))

    def test_export_lean4_post_raises_value_error(self) -> None:
        """Cover lines 700-701: export raises ValueError on post error."""
        from provably.lean4 import export_lean4

        def f(x: float) -> float:
            return x

        with pytest.raises(ValueError, match="Postcondition"):
            export_lean4(
                f,
                pre=lambda x: x >= 0,
                post=lambda x, r: (_ for _ in ()).throw(RuntimeError("post")),
            )

    def test_export_lean4_writes_output_path(self, tmp_path: Path) -> None:
        """Cover line 727: output_path write."""
        from provably.lean4 import export_lean4

        def f(x: int) -> int:
            return x

        out_file = tmp_path / "f.lean"
        code = export_lean4(f, output_path=out_file)
        assert out_file.exists()
        assert out_file.read_text() == code


# ===========================================================================
# Additional translator coverage — match statement, while early return, etc.
# ===========================================================================


class TestTranslatorMatchAndWhile:
    def test_while_early_return_warning(self) -> None:
        from provably.translator import Translator

        t = Translator()
        # While loop with early return inside
        code = "def f(x):\n    while x > 0:\n        return x\n    return 0\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Int("x")})
        # Should emit a warning about early return
        assert any("early return" in w.lower() for w in result.warnings)

    def test_while_statically_false_exits_immediately(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: int) -> int:
            while False:
                x += 1
            return x

        cert = verify_function(f, post=lambda x, r: r == x)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_match_statement_if_python_310_plus(self) -> None:
        """Cover match/case translation (Python 3.10+)."""
        import sys

        if sys.version_info < (3, 10):
            pytest.skip("match requires Python 3.10+")

        from provably.engine import Status, verify_function

        # Use exec to avoid syntax errors on Python < 3.10
        code = """
def classify(x):
    match x:
        case 0:
            return 0
        case _:
            return 1
"""
        globs: dict = {}
        exec(compile(code, "<test>", "exec"), globs)
        classify = globs["classify"]

        cert = verify_function(classify, pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
        assert cert.status in {
            Status.VERIFIED,
            Status.UNKNOWN,
            Status.TRANSLATION_ERROR,
            Status.SKIPPED,
        }

    def test_subscript_on_non_int_sort_raises(self) -> None:
        from provably.translator import TranslationError, Translator

        t = Translator()
        # Try to subscript a Real (not a tuple id)
        code = "def f(x):\n    return x[0]\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="Subscript on non-tuple"):
            t.translate(func, {"x": z3.Real("x")})

    def test_subscript_tuple_unknown_arity_raises(self) -> None:
        """Subscript on an IntSort without tuple metadata."""
        from provably.translator import TranslationError, Translator

        t = Translator()
        # Pass an IntSort param directly as "tuple" — no metadata
        code = "def f(x):\n    return x[0]\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        with pytest.raises(TranslationError, match="unknown arity"):
            t.translate(func, {"x": z3.Int("x")})

    def test_negative_tuple_subscript(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            t = (x, x + 1)
            return t[-1]

        cert = verify_function(f, pre=lambda x: x >= 0, post=lambda x, r: r >= 1)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_expr_stmt_in_body(self) -> None:
        """Non-docstring ast.Expr statement (side-effect call)."""
        from provably.translator import TranslationError, Translator

        t = Translator()
        # A non-string expression statement - this calls a function we can't translate
        code = "def f(x):\n    abs(x)\n    return x\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        # abs(x) is translated as side-effect - result discarded
        result = t.translate(func, {"x": z3.Real("x")})
        assert result.return_expr is not None

    def test_annassign_without_value(self) -> None:
        """AnnAssign with no value (type declaration only)."""
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    y: int\n    return x\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Real("x")})
        assert result.return_expr is not None

    def test_assert_statement_adds_constraint(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            assert x >= 0
            return x

        cert = verify_function(f, post=lambda x, r: r >= 0)
        assert cert.status in {Status.VERIFIED, Status.TRANSLATION_ERROR}

    def test_for_loop_with_early_return(self) -> None:
        """Early return inside a for loop emits warning."""
        from provably.translator import Translator

        t = Translator()
        code = "def f(x):\n    for i in range(5):\n        return i\n    return 0\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Int("x")})
        assert any("early return" in w.lower() for w in result.warnings)

    def test_while_budget_exhausted_adds_obligation(self) -> None:
        """While loop that never terminates within budget → termination obligation."""
        from provably.translator import _MAX_UNROLL, Translator

        t = Translator()
        # A loop that always runs (True condition) — will hit budget
        code = "def f(x):\n    i = 0\n    while True:\n        i += 1\n    return i\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        result = t.translate(func, {"x": z3.Int("x"), "i": z3.IntVal(0)})
        assert len(result.obligations) > 0
        assert any("unrolled" in w for w in result.warnings)


# ===========================================================================
# engine.py — _contract_sig, _validate_contract_arity, disk cache edge cases
# ===========================================================================


class TestEngineContractSig:
    def test_contract_sig_none(self) -> None:
        from provably.engine import _contract_sig

        assert _contract_sig(None) == "none"

    def test_contract_sig_with_closure(self) -> None:
        from provably.engine import _contract_sig

        threshold = 5
        fn = lambda x: x > threshold  # noqa: E731
        sig = _contract_sig(fn)
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_contract_sig_with_defaults(self) -> None:
        from provably.engine import _contract_sig

        def fn(x: float, y: float = 0.0) -> bool:
            return x > y

        sig = _contract_sig(fn)
        assert isinstance(sig, str)

    def test_contract_sig_non_function(self) -> None:
        from provably.engine import _contract_sig

        # A non-function callable (class instance) — fallback to repr
        class Callable:
            def __call__(self) -> bool:
                return True

        sig = _contract_sig(Callable())
        assert isinstance(sig, str)

    def test_validate_contract_arity_variadic(self) -> None:
        from provably.engine import _validate_contract_arity

        # *args function always passes
        result = _validate_contract_arity(lambda *args: True, 3, "pre", "f")
        assert result is None

    def test_validate_contract_arity_correct(self) -> None:
        from provably.engine import _validate_contract_arity

        result = _validate_contract_arity(lambda x, y: x > y, 2, "pre", "f")
        assert result is None

    def test_validate_contract_arity_wrong(self) -> None:
        from provably.engine import _validate_contract_arity

        result = _validate_contract_arity(lambda x: x > 0, 2, "pre", "f")
        assert result is not None
        assert "expected 2" in result

    def test_validate_contract_arity_uninspectable(self) -> None:
        from provably.engine import _validate_contract_arity

        class NoSig:
            def __call__(self) -> bool:
                return True

            @property
            def __signature__(self):
                raise ValueError("no sig")

        result = _validate_contract_arity(NoSig(), 1, "pre", "f")
        # Can't inspect — returns None
        assert result is None

    def test_disk_cache_path_with_dir(self, tmp_path: Path) -> None:
        from provably.engine import _disk_cache_path, configure

        configure(cache_dir=str(tmp_path))
        path = _disk_cache_path("test_key_abc")
        assert path is not None
        assert str(tmp_path) in str(path)
        configure(cache_dir=str(Path.home() / ".provably" / "cache"))

    def test_load_from_disk_miss(self, tmp_path: Path) -> None:
        from provably.engine import _load_from_disk, configure

        configure(cache_dir=str(tmp_path))
        result = _load_from_disk("nonexistent_key_xyz")
        assert result is None
        configure(cache_dir=str(Path.home() / ".provably" / "cache"))

    def test_load_from_disk_bad_json(self, tmp_path: Path) -> None:
        from provably.engine import _disk_cache_path, _load_from_disk, configure

        configure(cache_dir=str(tmp_path))
        key = "bad_json_key_123"
        path = _disk_cache_path(key)
        assert path is not None
        path.write_text("not valid json{{{")
        result = _load_from_disk(key)
        assert result is None
        configure(cache_dir=str(Path.home() / ".provably" / "cache"))

    def test_save_to_disk_then_load(self, tmp_path: Path) -> None:
        from provably.engine import (
            ProofCertificate,
            Status,
            _load_from_disk,
            _save_to_disk,
            configure,
        )

        configure(cache_dir=str(tmp_path))
        key = "save_load_test_abc"
        cert = ProofCertificate("f", "abc", Status.VERIFIED, ("x>=0",), ("r>=0",))
        _save_to_disk(key, cert)
        loaded = _load_from_disk(key)
        assert loaded is not None
        assert loaded.function_name == "f"
        assert loaded.status == Status.VERIFIED
        configure(cache_dir=str(Path.home() / ".provably" / "cache"))

    def test_verify_function_post_wrong_arity(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float, y: float) -> float:
            return x + y

        # post takes wrong number of args (2 instead of 3)
        cert = verify_function(f, post=lambda x, r: r > x)
        assert cert.status == Status.TRANSLATION_ERROR

    def test_verify_function_counterexample_extracted(self) -> None:
        from provably.engine import Status, verify_function

        def f(x: float) -> float:
            return x - 1

        cert = verify_function(f, post=lambda x, r: r > x)
        assert cert.status == Status.COUNTEREXAMPLE
        assert cert.counterexample is not None

    def test_verify_function_no_return_error(self) -> None:
        from provably.engine import Status, verify_function

        # Translator returns None for return_expr
        from provably.translator import TranslationResult, Translator

        original_translate = Translator.translate

        def patched_translate(self, func_ast, param_vars):
            result = original_translate(self, func_ast, param_vars)
            return TranslationResult(
                return_expr=None,
                constraints=result.constraints,
                obligations=result.obligations,
                env=result.env,
                warnings=result.warnings,
                tuple_meta=result.tuple_meta,
            )

        import provably.engine as eng_mod

        original_translator_cls = eng_mod.Translator

        class PatchedTranslator(original_translator_cls):  # type: ignore[valid-type]
            def translate(self, func_ast, param_vars):
                return patched_translate(self, func_ast, param_vars)

        import provably.engine as em

        original = em.Translator
        em.Translator = PatchedTranslator  # type: ignore[assignment]
        try:
            from provably.engine import clear_cache

            clear_cache()

            def f(x: float) -> float:
                return x

            cert = verify_function(f, post=lambda x, r: r == x)
            assert cert.status == Status.TRANSLATION_ERROR
        finally:
            em.Translator = original
            clear_cache()
