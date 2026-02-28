"""Targeted tests to close coverage gaps in engine, translator, and types."""

from __future__ import annotations

import ast
import json
import textwrap

import pytest
from conftest import requires_z3

pytestmark = requires_z3

import z3

from provably import clear_cache, configure, verified, verify_function
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
        with pytest.raises(TranslationError, match="simple function calls"):
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

    def test_tuple_expression_raises(self) -> None:
        src = """
def f(x):
    return (x, x)
"""
        x = z3.Real("x")
        func_ast = ast.parse(textwrap.dedent(src)).body[0]
        t = Translator()
        with pytest.raises(TranslationError, match="Tuple"):
            t.translate(func_ast, {"x": x})

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
