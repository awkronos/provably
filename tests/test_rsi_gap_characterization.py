"""W26-PROV1: characterization tests closing code-map RSI coverage rows.

Each test names the RSI row (generation ec12384b) and the uncovered source
region it pins.  Characterization tests deliberately pin CURRENT behavior —
they pass against untouched main; a future breakage turns them red.

Rows addressed here:
  - risk 60.0  examples/compositionality.py      (zero test touch)
  - risk 60.0  examples/refinement_types.py      (zero test touch)
  - risk 132.3 tests/test_coverage_95.py         (lean4.py residual lines)
  - risk 106.4 tests/test_final_coverage.py      (hypothesis nested Annotated)
  - risk 71.4  tests/test_coverage_boost.py      (_version fallback path)
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
EXAMPLES = REPO / "examples"

# ---------------------------------------------------------------------------
# row: risk 60.0 examples/compositionality.py — zero test touch.
# The example is a runnable script whose doc claims (Q.E.D. proofs,
# contract-composition, and the deliberate TRANSLATION_ERROR demo) rot
# silently.  Run it as its users do and pin the observable behavior.
# ---------------------------------------------------------------------------


def _run_example(name: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(REPO),
        env=env,
    )


class TestCompositionalityExampleCharacterization:
    """Row projects/provably/examples/compositionality.py (risk 60.0)."""

    @pytest.fixture(scope="class")
    def result(self) -> subprocess.CompletedProcess[str]:
        return _run_example("compositionality.py")

    def test_script_exits_zero(self, result) -> None:
        assert result.returncode == 0, result.stderr

    def test_primitives_all_qed(self, result) -> None:
        for fn in ("safe_half", "safe_max", "complement"):
            assert f"Q.E.D.    {fn}" in result.stdout

    def test_contract_composition_verifies_quarter(self, result) -> None:
        assert "quarter (via safe_half contract): [Q.E.D.] quarter" in result.stdout
        assert "quarter(8.0) = 2.0" in result.stdout

    def test_verify_module_pattern_all_proven(self, result) -> None:
        assert "All functions proven: True" in result.stdout

    def test_missing_contract_demo_translation_error(self, result) -> None:
        # The script's own expectation (line 196): without a contract the
        # verifier cannot see safe_half — pinned, or the demo silently
        # starts "succeeding" and the docs teach the wrong lesson.
        assert "bad_quarter (no contract): translation_error" in result.stdout

    def test_refinement_composition_roundtrip(self, result) -> None:
        assert "unit_to_percent(0.75) = 75.0" in result.stdout
        assert "percent_to_unit(75.0) = 0.75" in result.stdout


# ---------------------------------------------------------------------------
# row: risk 60.0 examples/refinement_types.py — zero test touch.
# ---------------------------------------------------------------------------


class TestRefinementTypesExampleCharacterization:
    """Row projects/provably/examples/refinement_types.py (risk 60.0)."""

    @pytest.fixture(scope="class")
    def result(self) -> subprocess.CompletedProcess[str]:
        return _run_example("refinement_types.py")

    def test_script_exits_zero(self, result) -> None:
        assert result.returncode == 0, result.stderr

    def test_all_honest_proofs_qed(self, result) -> None:
        for fn in (
            "nonneg_double",
            "bounded_scale",
            "positive_ratio",
            "to_unit",
            "lerp_unit",
            "safe_normalize",
            "clamp",
        ):
            assert f"[Q.E.D.] {fn}" in result.stdout

    def test_annotation_violation_detected_with_counterexample(self, result) -> None:
        # wrong_abs is a planted bug; the example's whole point (§6) is that
        # the verifier reports it.  Pin both the status and the witness.
        assert "wrong_abs: [DISPROVED] wrong_abs" in result.stdout
        assert "Status: counterexample" in result.stdout
        assert "Counterexample: {'x': -1.0, '__return__': -1.0}" in result.stdout

    def test_runtime_values_survive_verification(self, result) -> None:
        assert "nonneg_double(5) = 10" in result.stdout
        assert "bounded_scale(0.5) = 50.0" in result.stdout
        assert "positive_ratio(3, 4) = 7" in result.stdout
        assert "to_unit(7.5) = 0.75" in result.stdout
        assert "lerp_unit(0.2, 0.8, 0.5) = 0.5" in result.stdout
        assert "safe_normalize(10.0, 4.0) = 2.5" in result.stdout
        assert "clamp(15, 0, 10) = 10" in result.stdout
        assert "clamp(-3, 0, 10) = 0" in result.stdout

    def test_convenience_aliases_branch_taken(self, result) -> None:
        # The try/except at §7 has BOTH branches documented; current source
        # has Positive/UnitInterval, so the success branch is what runs.
        assert "scale_positive (Positive): [Q.E.D.] scale_positive" in result.stdout
        assert "clip_unit (UnitInterval):  [Q.E.D.] clip_unit" in result.stdout


# ---------------------------------------------------------------------------
# rows: risk 132.3/106.4/71.4 test-coverage trio — lean4.py pure-translation
# residuals (lines 87-99, 160, 224, 238, 249, 257, 276 per coverage report).
# ---------------------------------------------------------------------------

from provably import lean4 as L  # noqa: E402
from provably.hypothesis import from_refinements  # noqa: E402


def _ann(code: str) -> ast.expr:
    """Parse ``def f(x: <code>): ...`` and return the annotation AST node."""
    tree = ast.parse(f"def f(x: {code}): ...")
    return tree.body[0].args.args[0].annotation


def _stmts(body: str) -> list[ast.stmt]:
    tree = ast.parse("def _p():\n" + textwrap_indent(body))
    return tree.body[0].body  # type: ignore[union-attr]


def textwrap_indent(body: str) -> str:
    return "\n".join("    " + line for line in body.splitlines()) + "\n"


class TestLean4AstAnnotationResiduals:
    """lean4.py:87-99 — Annotated-subscript arms of _ast_annotation_type."""

    def test_plain_name_int(self) -> None:
        assert L._ast_annotation_type(_ann("int")) is int

    def test_plain_name_bool(self) -> None:
        assert L._ast_annotation_type(_ann("bool")) is bool

    def test_string_annotation(self) -> None:
        assert L._ast_annotation_type(_ann("'float'")) is float

    def test_annotated_subscript_returns_base(self) -> None:
        assert L._ast_annotation_type(_ann("Annotated[float, Ge(0)]")) is float

    def test_annotated_attribute_head(self) -> None:
        # typing.Annotated[...] reaches the Attribute arm (line ~92-94)
        assert L._ast_annotation_type(_ann("typing.Annotated[int, Ge(0)]")) is int

    def test_non_annotated_subscript_is_none(self) -> None:
        assert L._ast_annotation_type(_ann("list[int]")) is None

    def test_annotated_tuple_slice_recurses(self) -> None:
        assert L._ast_annotation_type(_ann("Annotated[bool, 'x']")) is bool


class TestLean4StatementResiduals:
    """lean4.py:160, 224, 238, 249, 257, 276 — _statements_to_lean raises."""

    def test_bare_return_rejected(self) -> None:
        with pytest.raises(ValueError, match="bare return"):
            L._statements_to_lean(_stmts("return"), {})

    def test_assignment_to_non_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="local names"):
            L._statements_to_lean(_stmts("obj.x = 1"), {})

    def test_ann_assign_without_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="named initialized annotation"):
            L._statements_to_lean(_stmts("x: int"), {})

    def test_ann_assign_non_name_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="named initialized annotation"):
            L._statements_to_lean(_stmts("obj.x: int = 1"), {})

    def test_aug_assign_non_name_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="augmented assignment"):
            L._statements_to_lean(_stmts("obj.x += 1"), {})

    def test_unsupported_statement_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported Lean4 statement"):
            L._statements_to_lean(_stmts("for i in [1]:\n        pass"), {})

    def test_unsupported_comparison_rejected(self) -> None:
        # `is` is the unsupported Compare op; operands must be translatable,
        # so use env-bound names (a list literal would die first with
        # "Unsupported Lean4 expression: List").
        with pytest.raises(ValueError, match="Unsupported Lean4 comparison"):
            L._statements_to_lean(_stmts("return a is b"), {"a": "a", "b": "b"})


class TestLean4FreshResultSymbol:
    """lean4.py:459 — the collision arm of _fresh_result_symbol."""

    def test_plain_when_no_collision(self) -> None:
        assert L._fresh_result_symbol(["x", "y"]) == "__provably_result"

    def test_suffixes_on_collision(self) -> None:
        name = L._fresh_result_symbol(["__provably_result"])
        assert name == "__provably_result_"
        assert name not in {"__provably_result"}

    def test_multiple_collisions_all_avoided(self) -> None:
        params = ["__provably_result", "__provably_result_"]
        name = L._fresh_result_symbol(params)
        assert name not in params


# ---------------------------------------------------------------------------
# row: risk 106.4 test_final_coverage.py — hypothesis.py:85-87 nested
# Annotated resolution loop (zero test touch: nothing in the suite builds a
# doubly-Annotated type).
# ---------------------------------------------------------------------------


class TestHypothesisNestedAnnotated:
    from hypothesis import given

    from provably.types import Ge, Le, Lt

    _OUTER = Annotated[Annotated[int, Le(100)], Ge(0)]  # nested — hits hypothesis.py:85-87
    _TRIPLE = Annotated[Annotated[Annotated[int, Ge(0)], Lt(50)], Ge(10)]

    @given(x=from_refinements(_OUTER))
    def test_nested_annotated_int_resolves_to_inner_base(self, x: int) -> None:
        assert isinstance(x, int)
        assert 0 <= x <= 100

    @given(x=from_refinements(_TRIPLE))
    def test_triple_nested(self, x: int) -> None:
        assert 10 <= x < 50


# ---------------------------------------------------------------------------
# row: risk 71.4 test_coverage_boost.py — _version.py:26-36 fallback branch
# (installed-metadata is always present in the venv, so the never-installed
# checkout path has zero test touch).
# ---------------------------------------------------------------------------


class TestVersionManifestFallback:
    """read_version() must fall back to the repository manifest when the
    distribution metadata is missing, and degrade to '0+unknown' honestly."""

    def test_fallback_reads_pyproject_manifest(self) -> None:
        from importlib.metadata import PackageNotFoundError

        from provably import _version

        def fake_version(_name: str) -> str:
            raise PackageNotFoundError(_name)

        with mock.patch.object(_version, "version", fake_version):
            got = _version.read_version()
        manifest = Path(SRC).parent / "pyproject.toml"
        text = manifest.read_text(encoding="utf-8")
        import re

        match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
        assert match, "worktree pyproject must carry a version key"
        assert got == match.group(1)

    def test_missing_manifest_returns_unknown(self, tmp_path: Path) -> None:
        from importlib.metadata import PackageNotFoundError

        from provably import _version

        def fake_version(_name: str) -> str:
            raise PackageNotFoundError(_name)

        real_path = Path(_version.__file__)
        ghost = tmp_path / "deep" / "pkg" / "_version.py"
        ghost.parent.mkdir(parents=True)
        ghost.write_text("")
        with mock.patch.object(_version, "version", fake_version), mock.patch.object(
            Path, "resolve", lambda self: ghost if self == real_path else real_path
        ):
            assert _version.read_version() == "0+unknown"

    def test_manifest_without_version_returns_unknown(self, tmp_path: Path) -> None:
        from importlib.metadata import PackageNotFoundError

        from provably import _version

        root = tmp_path / "checkout"
        (root / "src" / "provably").mkdir(parents=True)
        (root / "pyproject.toml").write_text('[project]\nname = "provably"\n')
        ghost = root / "src" / "provably" / "_version.py"
        ghost.write_text("")
        real_path = Path(_version.__file__)

        def fake_version(_name: str) -> str:
            raise PackageNotFoundError(_name)

        with mock.patch.object(_version, "version", fake_version), mock.patch.object(
            Path, "resolve", lambda self: ghost if self == real_path else real_path
        ):
            assert _version.read_version() == "0+unknown"
