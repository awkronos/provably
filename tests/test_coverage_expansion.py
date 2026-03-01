"""Coverage expansion tests — targeting every uncovered branch.

Organized by module and line number to systematically close coverage gaps.
"""

from __future__ import annotations

import ast
import sys
import textwrap

import pytest
import z3

from provably import verify_function
from provably.translator import (
    TranslationError,
    Translator,
    _z3_bool_cast,
    _z3_float_cast,
    _z3_int_cast,
    _z3_pow,
)

# =============================================================================
# translator.py — while-loop branches
# =============================================================================


class TestWhileLoopBranches:
    """Cover while-loop else, early return, max-unroll paths."""

    def test_while_else_clause_warning(self) -> None:
        """Line 482-483: while/else produces warning."""
        src = """
def f(x):
    while x > 0:
        x = x - 1
    else:
        x = x + 100
    return x
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        result = t.translate(func_ast, {"x": x})
        assert any("else clause ignored" in w for w in result.warnings)

    def test_while_early_return(self) -> None:
        """Lines 496-501: early return inside while body."""
        src = """
def f(x):
    while x > 0:
        return x
    return 0
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        result = t.translate(func_ast, {"x": x})
        assert any("Early return inside while" in w for w in result.warnings)

    def test_while_static_false_exits_immediately(self) -> None:
        """Lines 488-490: while False breaks immediately."""
        src = """
def f(x):
    while False:
        x = x + 1
    return x
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        assert len(result.warnings) == 0  # No max-unroll warning


# =============================================================================
# translator.py — match/case branches
# =============================================================================


class TestMatchCaseBranches:
    """Cover match/case pattern types."""

    @pytest.mark.skipif(sys.version_info < (3, 10), reason="match/case requires 3.10+")
    def test_match_singleton_pattern(self) -> None:
        """MatchSingleton: case True/False/None."""
        src = """
def f(x):
    match x:
        case True:
            return 1
        case False:
            return 0
        case _:
            return -1
"""
        x = z3.Bool("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": bool})
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

    @pytest.mark.skipif(sys.version_info < (3, 10), reason="match/case requires 3.10+")
    def test_match_with_guard(self) -> None:
        """Match case with guard clause: case X if cond."""
        src = """
def f(x):
    match x:
        case 1 if x > 0:
            return 10
        case _:
            return 0
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

    @pytest.mark.skipif(sys.version_info < (3, 10), reason="match/case requires 3.10+")
    def test_match_unsupported_pattern_raises(self) -> None:
        """Unsupported pattern type (e.g., MatchSequence) raises."""
        src = """
def f(x):
    match x:
        case [1, 2]:
            return 1
        case _:
            return 0
"""
        x = z3.Int("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator({"x": int})
        with pytest.raises(TranslationError, match="Unsupported match pattern"):
            t.translate(func_ast, {"x": x})


# =============================================================================
# translator.py — tuple and subscript edge cases
# =============================================================================


class TestTupleSubscriptEdgeCases:
    """Cover empty tuple, multi-element tuple, subscript on tuple."""

    def test_empty_tuple(self) -> None:
        """Line 845-846: empty tuple returns IntVal(0)."""
        src = """
def f(x):
    return ()
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None

    def test_three_element_tuple(self) -> None:
        """Lines 850-862: multi-element tuple creates accessors."""
        src = """
def f(x):
    return (x, x + 1, x + 2)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        # Should have 3 accessor constraints
        assert len(result.constraints) >= 3

    def test_tuple_unpack_non_name_target_raises(self) -> None:
        """Tuple unpacking with non-Name target raises."""
        src = """
def f(x):
    a[0], b = (x, x)
    return a
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Unsupported unpack target"):
            t.translate(func_ast, {"x": x})


# =============================================================================
# translator.py — builtin edge cases
# =============================================================================


class TestBuiltinEdgeCases:
    """Cover new builtin branches."""

    def test_pow_exponent_0_real(self) -> None:
        """_pow with exponent 0 on Real base returns RealVal 1."""
        t = Translator()
        base = z3.Real("x")
        exp = z3.IntVal(0)
        result = t._pow(base, exp)
        assert result.sort() == z3.RealSort()

    def test_pow_exponent_0_int(self) -> None:
        """_pow with exponent 0 on Int base returns IntVal 1."""
        t = Translator()
        base = z3.Int("x")
        exp = z3.IntVal(0)
        result = t._pow(base, exp)
        assert result.sort() == z3.IntSort()

    def test_pow_exponent_3(self) -> None:
        """_pow with exponent 3."""
        t = Translator()
        base = z3.Real("x")
        exp = z3.IntVal(3)
        result = t._pow(base, exp)
        assert result is not None

    def test_pow_real_integer_exponent(self) -> None:
        """_pow with RealVal that's actually integer (e.g., 2.0)."""
        t = Translator()
        base = z3.Real("x")
        exp = z3.RealVal("2")
        result = t._pow(base, exp)
        assert result is not None  # Should work (2.0 is integer)

    def test_pow_real_noninteger_raises(self) -> None:
        """_pow with truly non-integer exponent raises."""
        t = Translator()
        base = z3.Real("x")
        exp = z3.RealVal("2.5")
        with pytest.raises(TranslationError):
            t._pow(base, exp)

    def test_bool_cast_on_bool(self) -> None:
        """bool(True) returns BoolVal."""
        result = _z3_bool_cast(z3.BoolVal(True))
        assert result.sort() == z3.BoolSort()

    def test_bool_cast_on_int(self) -> None:
        """bool(0) returns False-equivalent."""
        result = _z3_bool_cast(z3.IntVal(0))
        assert result.sort() == z3.BoolSort()

    def test_int_cast_on_int(self) -> None:
        """int(x) where x is already int returns x."""
        x = z3.Int("x")
        result = _z3_int_cast(x)
        assert result is x

    def test_int_cast_on_real(self) -> None:
        """int(x) where x is real returns ToInt(x)."""
        x = z3.Real("x")
        result = _z3_int_cast(x)
        assert result.sort() == z3.IntSort()

    def test_int_cast_on_bool(self) -> None:
        """int(True) returns If(True, 1, 0)."""
        x = z3.BoolVal(True)
        result = _z3_int_cast(x)
        assert result.sort() == z3.IntSort()

    def test_float_cast_on_real(self) -> None:
        """float(x) where x is already real returns x."""
        x = z3.Real("x")
        result = _z3_float_cast(x)
        assert result is x

    def test_float_cast_on_int(self) -> None:
        """float(x) where x is int returns ToReal(x)."""
        x = z3.Int("x")
        result = _z3_float_cast(x)
        assert result.sort() == z3.RealSort()

    def test_float_cast_on_bool(self) -> None:
        """float(True) returns If(True, 1.0, 0.0)."""
        x = z3.BoolVal(True)
        result = _z3_float_cast(x)
        assert result.sort() == z3.RealSort()

    def test_len_wrong_arity_raises(self) -> None:
        """len() with wrong number of args."""
        src = """
def f(x, y):
    return len(x, y)
"""
        x = z3.Int("x")
        y = z3.Int("y")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="len.*1 argument"):
            t.translate(func_ast, {"x": x, "y": y})


# =============================================================================
# translator.py — walrus operator edge cases
# =============================================================================


class TestWalrusEdgeCases:
    """Cover walrus operator assignment into env."""

    def test_walrus_updates_env(self) -> None:
        """NamedExpr updates the environment."""
        src = """
def f(x):
    y = (z := x + 1)
    return y + z
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        assert "z" in result.env


# =============================================================================
# lean4.py — coverage expansion
# =============================================================================


class TestLean4Coverage:
    """Cover lean4.py uncovered branches."""

    def test_py_type_to_lean_int(self) -> None:
        from provably.lean4 import _py_type_to_lean
        assert _py_type_to_lean(int) == "Int"

    def test_py_type_to_lean_bool(self) -> None:
        from provably.lean4 import _py_type_to_lean
        assert _py_type_to_lean(bool) == "Bool"

    def test_py_type_to_lean_none(self) -> None:
        from provably.lean4 import _py_type_to_lean
        assert _py_type_to_lean(None) == "Float"

    def test_expr_to_lean_bool_constant(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.Constant(value=True)
        assert _expr_to_lean(node) == "true"
        node = ast.Constant(value=False)
        assert _expr_to_lean(node) == "false"

    def test_expr_to_lean_binop(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.BinOp(
            left=ast.Name(id="x"),
            op=ast.Add(),
            right=ast.Constant(value=1),
        )
        result = _expr_to_lean(node)
        assert "+" in result

    def test_expr_to_lean_unaryop(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.UnaryOp(op=ast.USub(), operand=ast.Name(id="x"))
        result = _expr_to_lean(node)
        assert "-" in result

    def test_expr_to_lean_compare_chain(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.Compare(
            left=ast.Name(id="a"),
            ops=[ast.Lt(), ast.Lt()],
            comparators=[ast.Name(id="b"), ast.Name(id="c")],
        )
        result = _expr_to_lean(node)
        assert "<" in result
        assert "∧" in result

    def test_expr_to_lean_boolop(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.BoolOp(
            op=ast.Or(),
            values=[ast.Name(id="a"), ast.Name(id="b")],
        )
        result = _expr_to_lean(node)
        assert "∨" in result

    def test_expr_to_lean_ifexp(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.IfExp(
            test=ast.Name(id="c"),
            body=ast.Name(id="a"),
            orelse=ast.Name(id="b"),
        )
        result = _expr_to_lean(node)
        assert "if" in result
        assert "then" in result

    def test_expr_to_lean_call_abs(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.Call(
            func=ast.Name(id="abs"),
            args=[ast.Name(id="x")],
            keywords=[],
        )
        result = _expr_to_lean(node)
        assert "|" in result or "abs" in result

    def test_expr_to_lean_unsupported(self) -> None:
        from provably.lean4 import _expr_to_lean
        node = ast.ListComp(elt=ast.Name(id="x"), generators=[])
        result = _expr_to_lean(node)
        assert "sorry" in result

    def test_if_to_lean_elif_chain(self) -> None:
        from provably.lean4 import _if_to_lean
        src = """
if x < 0:
    return -1
elif x > 0:
    return 1
else:
    return 0
"""
        tree = ast.parse(textwrap.dedent(src))
        if_stmt = tree.body[0]
        result = _if_to_lean(if_stmt, {"x": "x"})
        assert "if" in result
        # Should NOT contain sorry (elif is handled)
        assert "sorry" not in result

    def test_if_to_lean_no_else(self) -> None:
        from provably.lean4 import _if_to_lean
        src = """
if x < 0:
    return -1
"""
        tree = ast.parse(textwrap.dedent(src))
        if_stmt = tree.body[0]
        result = _if_to_lean(if_stmt, {"x": "x"})
        assert "sorry" in result  # Missing else gets sorry

    def test_func_body_augassign(self) -> None:
        from provably.lean4 import _func_body_to_lean
        src = """
def f(x):
    x += 1
    return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        result = _func_body_to_lean(func_ast, {"x": "x"})
        assert "let x" in result

    def test_func_body_pass(self) -> None:
        from provably.lean4 import _func_body_to_lean
        src = """
def f(x):
    pass
    return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        result = _func_body_to_lean(func_ast, {"x": "x"})
        assert "x" in result

    def test_func_body_docstring_skipped(self) -> None:
        from provably.lean4 import _func_body_to_lean
        src = '''
def f(x):
    """This is a docstring."""
    return x
'''
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        result = _func_body_to_lean(func_ast, {"x": "x"})
        assert "docstring" not in result

    def test_z3_str_to_lean_not_conversion(self) -> None:
        from provably.lean4 import _z3_str_to_lean
        result = _z3_str_to_lean("Not(x > 0)", ["x"])
        assert "¬" in result

    def test_check_lean4_proof_available(self) -> None:
        from provably.lean4 import HAS_LEAN4, check_lean4_proof
        if not HAS_LEAN4:
            pytest.skip("Lean4 not installed")
        # Simple Lean4 that should type-check
        ok, output = check_lean4_proof("#check Nat")
        # May or may not pass depending on imports, but shouldn't crash
        assert isinstance(ok, bool)
        assert isinstance(output, str)

    def test_check_lean4_proof_syntax_error(self) -> None:
        from provably.lean4 import HAS_LEAN4, check_lean4_proof
        if not HAS_LEAN4:
            pytest.skip("Lean4 not installed")
        ok, output = check_lean4_proof("this is not valid lean code !!!")
        assert not ok
        assert len(output) > 0

    def test_generate_theorem_not_function_def(self) -> None:
        from provably.lean4 import generate_lean4_theorem
        lean = generate_lean4_theorem(
            func_name="test",
            param_names=[],
            param_types={},
            pre_str=None,
            post_str=None,
            source="x = 42",
        )
        assert "Error" in lean or "sorry" in lean


# =============================================================================
# types.py — coverage expansion
# =============================================================================


class TestTypesModuleCoverage:
    """Cover types.py marker classes and edge cases."""

    def test_gt_init_and_repr(self) -> None:
        from provably.types import Gt
        g = Gt(5)
        assert g.bound == 5
        assert repr(g) == "Gt(5)"

    def test_ge_init_and_repr(self) -> None:
        from provably.types import Ge
        g = Ge(0)
        assert g.bound == 0
        assert repr(g) == "Ge(0)"

    def test_lt_init_and_repr(self) -> None:
        from provably.types import Lt
        lt = Lt(10)
        assert lt.bound == 10
        assert repr(lt) == "Lt(10)"

    def test_le_init_and_repr(self) -> None:
        from provably.types import Le
        le = Le(100)
        assert le.bound == 100
        assert repr(le) == "Le(100)"

    def test_between_init_and_repr(self) -> None:
        from provably.types import Between
        b = Between(0, 1)
        assert b.lo == 0
        assert b.hi == 1
        assert repr(b) == "Between(0, 1)"

    def test_noteq_init_and_repr(self) -> None:
        from provably.types import NotEq
        n = NotEq(42)
        assert n.val == 42
        assert repr(n) == "NotEq(42)"

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
        from typing import Annotated

        from provably.types import Gt, python_type_to_z3_sort
        assert python_type_to_z3_sort(Annotated[float, Gt(0)]) == z3.RealSort()

    def test_python_type_to_z3_sort_unknown_raises(self) -> None:
        from provably.types import python_type_to_z3_sort
        with pytest.raises(TypeError, match="No Z3 sort"):
            python_type_to_z3_sort(str)

    def test_make_z3_var_int(self) -> None:
        from provably.types import make_z3_var
        v = make_z3_var("x", int)
        assert v.sort() == z3.IntSort()

    def test_make_z3_var_bool(self) -> None:
        from provably.types import make_z3_var
        v = make_z3_var("b", bool)
        assert v.sort() == z3.BoolSort()

    def test_extract_refinements_gt(self) -> None:
        from typing import Annotated

        from provably.types import Gt, extract_refinements
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, Gt(0)], x)
        assert len(constraints) >= 1

    def test_extract_refinements_between(self) -> None:
        from typing import Annotated

        from provably.types import Between, extract_refinements
        x = z3.Real("x")
        constraints = extract_refinements(Annotated[float, Between(0, 1)], x)
        assert len(constraints) >= 2

    def test_extract_refinements_noteq(self) -> None:
        from typing import Annotated

        from provably.types import NotEq, extract_refinements
        x = z3.Int("x")
        constraints = extract_refinements(Annotated[int, NotEq(0)], x)
        assert len(constraints) >= 1

    def test_extract_refinements_bare_type(self) -> None:
        from provably.types import extract_refinements
        x = z3.Real("x")
        constraints = extract_refinements(float, x)
        assert len(constraints) == 0


# =============================================================================
# hypothesis.py — coverage expansion
# =============================================================================


class TestHypothesisCoverage:
    """Cover hypothesis.py uncovered paths."""

    def test_hypothesis_check_basic(self) -> None:
        from provably.hypothesis import hypothesis_check

        def double(x: float) -> float:
            return x * 2

        result = hypothesis_check(double, pre=lambda x: x >= 0, post=lambda x, result: result >= 0)
        assert result is not None
        assert hasattr(result, "passed")

    def test_hypothesis_check_failing(self) -> None:
        from provably.hypothesis import hypothesis_check

        def bad(x: float) -> float:
            return x - 1

        result = hypothesis_check(bad, pre=lambda x: x >= 0, post=lambda x, result: result >= 0)
        assert result is not None

    def test_from_refinements_positive(self) -> None:
        from provably.hypothesis import from_refinements
        from provably.types import Positive
        strat = from_refinements(Positive)
        assert strat is not None

    def test_from_refinements_unit_interval(self) -> None:
        from provably.hypothesis import from_refinements
        from provably.types import UnitInterval
        strat = from_refinements(UnitInterval)
        assert strat is not None

    def test_proven_property_decorator(self) -> None:
        from provably.hypothesis import proven_property

        @proven_property(
            pre=lambda x: x >= 0,
            post=lambda x, result: result >= 0,
        )
        def triple(x: float) -> float:
            return x * 3

        assert hasattr(triple, "__proof__")
        assert triple.__proof__.verified


# =============================================================================
# engine.py — coverage expansion
# =============================================================================


class TestEngineCoverage:
    """Cover engine.py edge cases."""

    def test_verify_function_no_return(self) -> None:
        """Function with no return on all paths."""
        def no_return(x: float) -> float:
            y = x + 1

        cert = verify_function(no_return, post=lambda x, result: result >= 0)
        assert cert.status.value in ("translation_error", "skipped")

    def test_verify_function_post_exception(self) -> None:
        """Post lambda that raises."""
        def good(x: float) -> float:
            return x

        def bad_post(x, result):
            raise ValueError("broken post")

        cert = verify_function(good, post=bad_post)
        assert cert.status.value == "translation_error"

    def test_verify_function_pre_exception(self) -> None:
        """Pre lambda that raises."""
        def good(x: float) -> float:
            return x

        def bad_pre(x):
            raise ValueError("broken pre")

        cert = verify_function(good, pre=bad_pre, post=lambda x, r: r == x)
        assert cert.status.value == "translation_error"

    def test_certificate_explain_verified(self) -> None:
        """Test explain() on a verified certificate."""
        def identity(x: float) -> float:
            return x

        cert = verify_function(identity, post=lambda x, r: r == x)
        explanation = cert.explain()
        assert "Q.E.D." in explanation

    def test_certificate_to_prompt_verified(self) -> None:
        """Test to_prompt() on verified cert."""
        def identity(x: float) -> float:
            return x

        cert = verify_function(identity, post=lambda x, r: r == x)
        prompt = cert.to_prompt()
        assert "verified" in prompt.lower() or "Q.E.D" in prompt

    def test_certificate_from_json_round_trip(self) -> None:
        """Test to_json/from_json round trip."""
        from provably.engine import ProofCertificate
        def identity(x: float) -> float:
            return x
        cert = verify_function(identity, post=lambda x, r: r == x)
        data = cert.to_json()
        restored = ProofCertificate.from_json(data)
        assert restored.function_name == cert.function_name
        assert restored.status == cert.status

    def test_certificate_str_verified(self) -> None:
        """Test __str__ on verified cert."""
        def identity(x: float) -> float:
            return x
        cert = verify_function(identity, post=lambda x, r: r == x)
        s = str(cert)
        assert "Q.E.D." in s
        assert "identity" in s

    def test_certificate_str_counterexample(self) -> None:
        """Test __str__ on counterexample cert."""
        def bad(x: float) -> float:
            return x
        cert = verify_function(bad, post=lambda x, r: r > x)
        s = str(cert)
        assert "DISPROVED" in s

    def test_explain_counterexample(self) -> None:
        """Test explain() on counterexample."""
        def bad(x: float) -> float:
            return x
        cert = verify_function(bad, post=lambda x, r: r > x)
        explanation = cert.explain()
        assert "Counterexample" in explanation
        assert "Postcondition" in explanation

    def test_to_prompt_counterexample(self) -> None:
        """Test to_prompt() on counterexample."""
        def bad(x: float) -> float:
            return x
        cert = verify_function(bad, post=lambda x, r: r > x)
        prompt = cert.to_prompt()
        assert "DISPROVED" in prompt or "counterexample" in prompt.lower()

    def test_verify_module(self) -> None:
        """Test verify_module on _self_proof."""
        import provably._self_proof as sp
        from provably import verify_module
        results = verify_module(sp)
        assert len(results) >= 10  # At least original 10

    def test_configure_log_level(self) -> None:
        """Test configure with log_level."""
        from provably import configure
        configure(log_level="DEBUG")
        configure(log_level="WARNING")  # Reset

    def test_configure_unknown_key_raises(self) -> None:
        """Test configure with unknown key."""
        from provably import configure
        with pytest.raises(ValueError, match="Unknown"):
            configure(nonexistent_key=True)

    def test_clear_cache(self) -> None:
        """Test clear_cache."""
        from provably import clear_cache
        clear_cache()  # Should not raise


# =============================================================================
# decorators.py — coverage expansion
# =============================================================================


class TestDecoratorsCoverage:
    """Cover decorators.py edge cases."""

    def test_runtime_checked_pre_violation(self) -> None:
        from provably import runtime_checked
        @runtime_checked(pre=lambda x: x > 0, raise_on_failure=True)
        def positive_only(x: float) -> float:
            return x
        with pytest.raises(Exception):  # noqa: B017
            positive_only(-1)

    def test_runtime_checked_post_violation(self) -> None:
        from provably import ContractViolationError, runtime_checked
        @runtime_checked(post=lambda x, result: result > 0, raise_on_failure=True)
        def returns_negative(x: float) -> float:
            return -x
        with pytest.raises(ContractViolationError):
            returns_negative(5)

    def test_verified_check_contracts_runtime(self) -> None:
        from provably import verified
        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
            check_contracts=True,
        )
        def safe_double(x: float) -> float:
            return x * 2
        assert safe_double(5) == 10
        assert safe_double.__proof__.verified

    def test_contract_violation_error_fields(self) -> None:
        from provably import ContractViolationError
        err = ContractViolationError("pre", "test_fn", (1, 2), None)
        assert err.kind == "pre"
        assert err.func_name == "test_fn"

    def test_verification_error_certificate(self) -> None:
        from provably import VerificationError
        from provably.engine import ProofCertificate, Status
        cert = ProofCertificate(
            function_name="test",
            source_hash="abc",
            status=Status.COUNTEREXAMPLE,
            preconditions=(),
            postconditions=("result > 0",),
            counterexample={"x": -1},
        )
        err = VerificationError(cert)
        assert err.certificate is cert
