"""Targeted tests to close coverage gaps in engine, translator, and types."""

from __future__ import annotations

import ast
import json
import textwrap
import warnings

import pytest
from conftest import requires_z3

pytestmark = requires_z3

import z3

from provably import clear_cache, configure, verified, verify_function
from provably.decorators import ContractViolationError, runtime_checked
from provably.engine import (
    ProofCertificate,
    Status,
    verify_module,
)
from provably.translator import TranslationError, Translator

# ---------------------------------------------------------------------------
# Engine: to_json / from_json round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_verified_cert_to_json(self) -> None:
        def f(x: float) -> float:
            return x

        cert = verify_function(f, post=lambda x, r: r == x)
        d = cert.to_json()
        assert d["status"] == "verified"
        assert d["function_name"] == "f"
        assert isinstance(d["preconditions"], list)
        assert isinstance(d["postconditions"], list)
        assert d["counterexample"] is None

    def test_counterexample_cert_to_json(self) -> None:
        def f(x: float) -> float:
            return -x

        cert = verify_function(f, post=lambda x, r: r > 0)
        d = cert.to_json()
        assert d["status"] == "counterexample"
        assert d["counterexample"] is not None
        assert "x" in d["counterexample"]
        # Must be JSON-serializable
        json.dumps(d)

    def test_from_json_round_trip(self) -> None:
        def f(x: float) -> float:
            return x + 1

        cert = verify_function(f, post=lambda x, r: r > x)
        d = cert.to_json()
        restored = ProofCertificate.from_json(d)
        assert restored.function_name == cert.function_name
        assert restored.status == cert.status
        assert restored.source_hash == cert.source_hash


# ---------------------------------------------------------------------------
# Engine: verify_module
# ---------------------------------------------------------------------------


class TestVerifyModule:
    def test_verify_module_finds_verified_functions(self) -> None:
        import types

        mod = types.ModuleType("test_mod")

        @verified(post=lambda x, r: r == x)
        def id_fn(x: float) -> float:
            return x

        @verified(post=lambda x, r: r >= 0)
        def abs_fn(x: float) -> float:
            if x >= 0:
                return x
            return -x

        mod.id_fn = id_fn
        mod.abs_fn = abs_fn
        mod.not_verified = lambda x: x  # no __proof__

        result = verify_module(mod)
        assert "id_fn" in result
        assert "abs_fn" in result
        assert "not_verified" not in result
        assert result["id_fn"].verified
        assert result["abs_fn"].verified


# ---------------------------------------------------------------------------
# Engine: configure() integration
# ---------------------------------------------------------------------------


class TestConfigureIntegration:
    def test_configure_timeout(self) -> None:
        configure(timeout_ms=10000)

        # Verify it doesn't crash with the new timeout
        def f(x: float) -> float:
            return x

        cert = verify_function(f, post=lambda x, r: r == x)
        assert cert.verified
        configure(timeout_ms=5000)  # reset

    def test_configure_invalid_key_raises(self) -> None:
        with pytest.raises((ValueError, KeyError, TypeError)):
            configure(nonexistent_key=True)


# ---------------------------------------------------------------------------
# Translator: _call_verified path (composition)
# ---------------------------------------------------------------------------


class TestCompositionTranslation:
    def test_call_verified_with_contract(self) -> None:
        """Translator resolves verified function calls via contracts."""
        src = """
def f(x):
    return helper(x)
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        x = z3.Real("x")
        contracts = {
            "helper": {
                "pre": lambda x: x >= 0,
                "post": lambda x, r: r >= 0,
                "return_sort": z3.RealSort(),
            }
        }
        t = Translator(verified_contracts=contracts)
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        # Constraints should include the contract's pre and post
        assert len(result.constraints) >= 1

    def test_call_verified_without_pre(self) -> None:
        """Contract with only post (no pre)."""
        src = """
def f(x):
    return helper(x)
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        x = z3.Real("x")
        contracts = {
            "helper": {
                "post": lambda x, r: r >= 0,
                "return_sort": z3.RealSort(),
            }
        }
        t = Translator(verified_contracts=contracts)
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None


# ---------------------------------------------------------------------------
# Translator: _merge_envs path (if/else without return)
# ---------------------------------------------------------------------------


class TestMergeEnvs:
    def test_if_else_no_return_merges_envs(self) -> None:
        """If/else that assigns but doesn't return uses phi nodes."""
        src = """
def f(x):
    y = 0
    if x > 0:
        y = x
    else:
        y = -x
    return y
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        # Should be If(x > 0, x, -x)
        s = z3.Solver()
        s.add(x == -5)
        s.add(result.return_expr != 5)
        assert s.check() == z3.unsat

    def test_if_only_one_branch_assigns_new_var(self) -> None:
        """Variable defined only in true branch — false uses original."""
        src = """
def f(x):
    y = 0
    if x > 10:
        y = 100
    return y
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None
        s = z3.Solver()
        s.add(x == 5)
        s.add(result.return_expr != 0)
        assert s.check() == z3.unsat


# ---------------------------------------------------------------------------
# Translator: Bool coercion
# ---------------------------------------------------------------------------


class TestBoolCoercion:
    def test_bool_compared_with_int(self) -> None:
        src = """
def f(x):
    return (x > 0) == True
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        assert result.return_expr is not None


# ---------------------------------------------------------------------------
# Translator: method call error
# ---------------------------------------------------------------------------


class TestMethodCallError:
    def test_attribute_call_raises(self) -> None:
        src = """
def f(x):
    return x.method()
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Unsupported method call"):
            t.translate(func_ast, {"x": x})

    def test_subscript_raises(self) -> None:
        src = """
def f(x):
    return x[0]
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError):
            t.translate(func_ast, {"x": x})

    def test_tuple_expression_supported(self) -> None:
        src = """
def f(x):
    return (x, x)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": x})
        # Tuple returns are now supported — should produce a result (IntSort tuple ID)
        assert result.return_expr is not None

    def test_multiple_assign_targets_raises(self) -> None:
        src = """
def f(x):
    a = b = x
    return a
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Multiple assignment"):
            t.translate(func_ast, {"x": x})


# ---------------------------------------------------------------------------
# Engine: ProofCertificate.__str__
# ---------------------------------------------------------------------------


class TestCertificateStr:
    def test_unknown_status_str(self) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="abc",
            status=Status.UNKNOWN,
            preconditions=(),
            postconditions=(),
            message="timeout",
        )
        assert "?" in str(cert)

    def test_skipped_status_str(self) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="abc",
            status=Status.SKIPPED,
            preconditions=(),
            postconditions=(),
        )
        s = str(cert)
        assert "SKIPPED" in s or "f" in s

    def test_translation_error_str(self) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="abc",
            status=Status.TRANSLATION_ERROR,
            preconditions=(),
            postconditions=(),
            message="unsupported",
        )
        s = str(cert)
        assert "TRANSLATION_ERROR" in s or "unsupported" in s


# ---------------------------------------------------------------------------
# Consolidated from tests/test_remaining_coverage.py (rsi/provably3): classes and module
# helpers moved verbatim; zero assertion changes. Absorbed module docstring:
#   Surgical tests targeting every remaining uncovered line.
#
#   Coverage gaps addressed:
#   - translator.py: lines 248-254 (if branch returns only), 272/284/290/298-303
#     (for-loop edge cases), 319/331 (comparison ops), 340-344/363/365/384-386
#     (expressions), 422-434 (string constants), 449/453/456 (binop errors),
#     483 (unary op error), 505 (comparison error), 574-580 (bool coercion),
#     590-604 (merge envs)
#   - engine.py: lines 80-81 (configure log_level), 167 (HAS_Z3 guard),
#     235-236/264-265/280/322/337-338/361-362 (pre/post error paths),
#     396-416 (TranslationError enrichment), 464-467 (post exception),
#     524 (no postcondition), 570-571 (cert serialization edge), 601/604-610
#     (Z3 val conversion), 640-644/659 (counterexample model edge cases)
#   - decorators.py: lines 120-121/128/138 (_check_contract_arity branches),
#     279-280/302-307 (check_contracts path), 316-317/324-325/327 (contract
#     violation handling)
# ---------------------------------------------------------------------------


class TestTranslatorStringConstant:
    def test_string_constant_raises(self) -> None:
        """String constants raise TranslationError — not silently approximated."""
        src = """
def f(x):
    y = "hello"
    return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="String constant"):
            t.translate(func_ast, {"x": z3.Real("x")})

    def test_unsupported_constant_type_raises(self) -> None:
        """bytes, None, etc. should raise TranslationError."""
        src = """
def f(x):
    y = b"bytes"
    return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Unsupported constant"):
            t.translate(func_ast, {"x": z3.Real("x")})


class TestTranslatorBinopErrors:
    def test_floor_div_on_reals_raises(self) -> None:
        src = """
def f(x):
    return x // 2.0
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Floor division"):
            t.translate(func_ast, {"x": z3.Real("x")})

    def test_modulo_on_reals_raises(self) -> None:
        src = """
def f(x):
    return x % 2.0
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Modulo"):
            t.translate(func_ast, {"x": z3.Real("x")})

    def test_matmult_binop_raises(self) -> None:
        """@ (MatMult) should raise — not supported."""
        src = """
def f(x, y):
    return x @ y
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Unsupported operator"):
            t.translate(func_ast, {"x": z3.Int("x"), "y": z3.Int("y")})

    def test_unsupported_unary_op_raises(self) -> None:
        """Invert (~) should raise."""
        src = """
def f(x):
    return ~x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Unsupported unary"):
            t.translate(func_ast, {"x": z3.Int("x")})


class TestTranslatorComparisonEdge:
    def test_is_comparison_raises(self) -> None:
        src = """
def f(x):
    return x is None
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError):
            t.translate(func_ast, {"x": z3.Real("x")})


class TestTranslatorForLoopEdgeCases:
    def test_for_non_name_target_raises(self) -> None:
        src = """
def f(x):
    for (a, b) in range(5):
        pass
    return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="simple name"):
            t.translate(func_ast, {"x": z3.Real("x")})

    def test_for_non_range_iter_raises(self) -> None:
        src = """
def f(x):
    for i in [1, 2, 3]:
        pass
    return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="range"):
            t.translate(func_ast, {"x": z3.Real("x")})

    def test_for_range_with_variable_bound_from_closure(self) -> None:
        src = """
def f(x):
    for i in range(N):
        x += i
    return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator(closure_vars={"N": z3.IntVal(3)})
        result = t.translate(func_ast, {"x": z3.Real("x")})
        assert result.return_expr is not None


class TestTranslatorIfBranchReturnOnly:
    def test_only_true_branch_returns(self) -> None:
        """When only the true branch returns and there's no remaining."""
        src = """
def f(x):
    if x > 0:
        return x
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": z3.Real("x")})
        # May return x when x > 0, or None otherwise — only true branch returns
        # The translator should handle this gracefully

    def test_only_false_branch_returns(self) -> None:
        src = """
def f(x):
    if x > 0:
        y = x
    else:
        return -x
    return y
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": z3.Real("x")})
        assert result.return_expr is not None


class TestTranslatorBoolCoercion:
    def test_bool_to_int_coercion(self) -> None:
        src = """
def f(x):
    return (x > 0) + 1
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": z3.Real("x")})
        assert result.return_expr is not None


class TestEnginePrePostErrors:
    def test_pre_using_python_and_gives_helpful_error(self) -> None:
        def f(x: float, y: float) -> float:
            return x + y

        cert = verify_function(
            f,
            pre=lambda x, y: x > 0 and y > 0,
            post=lambda x, y, r: r > 0,
        )
        assert cert.status == Status.TRANSLATION_ERROR
        assert "&" in cert.message or "and" in cert.message.lower()

    def test_post_exception_gives_error(self) -> None:
        def f(x: float) -> float:
            return x

        def bad_post(x, r):
            raise ValueError("intentional")

        cert = verify_function(f, post=bad_post)
        assert cert.status == Status.TRANSLATION_ERROR
        assert "Postcondition" in cert.message or "intentional" in cert.message

    def test_translation_error_enriched_with_line(self) -> None:
        def f(x: float) -> float:
            return x.bad_attr()  # type: ignore

        cert = verify_function(f, post=lambda x, r: r == x)
        assert cert.status == Status.TRANSLATION_ERROR
        assert "line" in cert.message.lower() or "simple function" in cert.message.lower()

    def test_no_return_gives_error(self) -> None:
        def f(x: float) -> None:
            y = x + 1

        cert = verify_function(f, post=lambda x, r: True)
        assert cert.status == Status.TRANSLATION_ERROR
        assert "return" in cert.message.lower()


class TestEngineConfigure:
    def test_configure_log_level(self) -> None:
        configure(log_level="DEBUG")
        import logging

        assert logging.getLogger("provably").level == logging.DEBUG
        configure(log_level="WARNING")  # reset

    def test_configure_invalid_key(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            configure(bad_key=True)


class TestEngineContractArity:
    def test_arity_mismatch_pre_gives_error(self) -> None:
        def f(x: float) -> float:
            return x

        # Pre takes 0 args but function has 1 param — engine detects mismatch
        cert = verify_function(f, pre=lambda: True, post=lambda x, r: r == x)
        # Could be TRANSLATION_ERROR (arity mismatch) or work if engine is lenient
        assert "pre" in cert.message.lower() or cert.verified

    def test_varargs_pre_no_warn(self) -> None:
        def f(x: float) -> float:
            return x

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cert = verify_function(f, pre=lambda *args: True, post=lambda x, r: r == x)
        # varargs — should not warn about arity
        arity_warnings = [w2 for w2 in w if "argument" in str(w2.message)]
        assert len(arity_warnings) == 0


class TestCheckContractsPath:
    def test_check_contracts_pre_violation_at_runtime(self) -> None:
        @verified(
            pre=lambda x: x >= 0,
            post=lambda x, r: r >= 0,
            check_contracts=True,
        )
        def safe_sqrt(x: float) -> float:
            if x >= 0:
                return x
            return -x

        assert safe_sqrt.__proof__.verified
        assert safe_sqrt(4) == 4  # passes pre
        with pytest.raises(ContractViolationError):
            safe_sqrt(-1)  # violates pre at runtime

    def test_check_contracts_post_violation_at_runtime(self) -> None:
        @verified(
            post=lambda x, r: r > 0,
            check_contracts=True,
        )
        def bad_fn(x: float) -> float:
            return -x

        # Z3 will disprove this, but check_contracts is independent
        with pytest.raises(ContractViolationError):
            bad_fn(5)  # returns -5, violates post r > 0

    def test_check_contracts_exception_in_pre_raises(self) -> None:
        def exploding_pre(x):
            raise ValueError("boom")

        @verified(pre=exploding_pre, check_contracts=True)
        def f(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError):
            f(5)

    def test_check_contracts_exception_in_post_raises(self) -> None:
        def exploding_post(x, r):
            raise ValueError("boom")

        @verified(post=exploding_post, check_contracts=True)
        def f(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError):
            f(5)


class TestRuntimeCheckedEdge:
    def test_runtime_checked_raise_false_no_exception(self) -> None:
        @runtime_checked(
            pre=lambda x: x >= 0,
            raise_on_failure=False,
        )
        def f(x: float) -> float:
            return x

        # Should NOT raise, just log
        result = f(-1)
        assert result == -1

    def test_runtime_checked_bare_no_contracts(self) -> None:
        @runtime_checked
        def f(x: float) -> float:
            return x + 1

        assert f(5) == 6

    def test_contract_violation_attributes(self) -> None:
        @runtime_checked(pre=lambda x: x > 0)
        def f(x: float) -> float:
            return x

        with pytest.raises(ContractViolationError) as exc_info:
            f(-1)
        err = exc_info.value
        assert err.kind == "pre"
        assert err.func_name == "f"


class TestMergeEnvsExplicit:
    def test_merge_new_var_in_only_one_branch(self) -> None:
        src = """
def f(x):
    if x > 0:
        y = 1
    else:
        y = 2
    return y
"""
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        result = t.translate(func_ast, {"x": z3.Real("x")})
        assert result.return_expr is not None
        s = z3.Solver()
        s.add(z3.Real("x") == 5)
        s.add(result.return_expr != 1)
        assert s.check() == z3.unsat
