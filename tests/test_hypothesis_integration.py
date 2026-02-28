"""Tests for provably.hypothesis — Hypothesis bridge and ProofCertificate extras."""

from __future__ import annotations

import math
from typing import Annotated

import pytest

from provably.engine import ProofCertificate, Status
from provably.hypothesis import (
    HypothesisResult,
    from_counterexample,
    from_refinements,
    hypothesis_check,
)
from provably.types import Between, Ge, Gt, Le, Lt, NotEq

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _draw_sample(strategy: object, n: int = 50) -> list[object]:
    """Draw *n* samples from a Hypothesis strategy (uses find/draw internally)."""
    from hypothesis import HealthCheck, given, settings

    results: list[object] = []

    @settings(max_examples=n, suppress_health_check=list(HealthCheck), deadline=None)
    @given(strategy)  # type: ignore[arg-type]
    def _collect(x: object) -> None:
        results.append(x)

    _collect()
    return results


# ---------------------------------------------------------------------------
# from_refinements — integers
# ---------------------------------------------------------------------------


class TestFromRefinementsInt:
    def test_from_refinements_int_ge(self) -> None:
        strategy = from_refinements(Annotated[int, Ge(0)])
        samples = _draw_sample(strategy, 100)
        assert all(isinstance(x, int) for x in samples)
        assert all(x >= 0 for x in samples), samples  # type: ignore[operator]

    def test_from_refinements_int_gt(self) -> None:
        strategy = from_refinements(Annotated[int, Gt(5)])
        samples = _draw_sample(strategy, 100)
        assert all(isinstance(x, int) for x in samples)
        assert all(x > 5 for x in samples), samples  # type: ignore[operator]
        # Minimum value should be 6
        assert min(samples) >= 6  # type: ignore[type-var]

    def test_from_refinements_multiple_markers(self) -> None:
        strategy = from_refinements(Annotated[int, Ge(0), Le(100)])
        samples = _draw_sample(strategy, 200)
        assert all(isinstance(x, int) for x in samples)
        assert all(0 <= x <= 100 for x in samples), samples  # type: ignore[operator]

    def test_from_refinements_noteq(self) -> None:
        strategy = from_refinements(Annotated[int, Ge(-10), Le(10), NotEq(0)])
        samples = _draw_sample(strategy, 200)
        assert all(isinstance(x, int) for x in samples)
        assert 0 not in samples, f"Expected no zeros, got: {samples}"


# ---------------------------------------------------------------------------
# from_refinements — floats
# ---------------------------------------------------------------------------


class TestFromRefinementsFloat:
    def test_from_refinements_float_between(self) -> None:
        strategy = from_refinements(Annotated[float, Between(0, 1)])
        samples = _draw_sample(strategy, 200)
        assert all(isinstance(x, float) for x in samples)
        assert all(0.0 <= x <= 1.0 for x in samples), samples  # type: ignore[operator]

    def test_from_refinements_float_lt(self) -> None:
        strategy = from_refinements(Annotated[float, Lt(10.0)])
        samples = _draw_sample(strategy, 200)
        assert all(isinstance(x, float) for x in samples)
        assert all(x < 10.0 for x in samples), samples  # type: ignore[operator]

    def test_from_refinements_float_ge(self) -> None:
        strategy = from_refinements(Annotated[float, Ge(0.0)])
        samples = _draw_sample(strategy, 100)
        assert all(x >= 0.0 for x in samples), samples  # type: ignore[operator]

    def test_from_refinements_float_le(self) -> None:
        strategy = from_refinements(Annotated[float, Le(5.0)])
        samples = _draw_sample(strategy, 100)
        assert all(x <= 5.0 for x in samples), samples  # type: ignore[operator]

    def test_from_refinements_float_gt(self) -> None:
        strategy = from_refinements(Annotated[float, Gt(0.0)])
        samples = _draw_sample(strategy, 100)
        assert all(x > 0.0 for x in samples), samples  # type: ignore[operator]


# ---------------------------------------------------------------------------
# from_refinements — bool
# ---------------------------------------------------------------------------


class TestFromRefinementsBool:
    def test_from_refinements_bool(self) -> None:
        strategy = from_refinements(bool)
        samples = _draw_sample(strategy, 50)
        assert all(isinstance(x, bool) for x in samples)
        # Should produce both True and False (probabilistically)
        assert set(samples) <= {True, False}


# ---------------------------------------------------------------------------
# from_refinements — unsupported type
# ---------------------------------------------------------------------------


class TestFromRefinementsUnsupported:
    def test_from_refinements_unsupported_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported base type"):
            from_refinements(str)

    def test_from_refinements_bare_int(self) -> None:
        # Bare int with no markers is valid
        strategy = from_refinements(int)
        samples = _draw_sample(strategy, 20)
        assert all(isinstance(x, int) for x in samples)

    def test_from_refinements_bare_float(self) -> None:
        strategy = from_refinements(float)
        samples = _draw_sample(strategy, 20)
        assert all(isinstance(x, float) for x in samples)
        assert all(not math.isnan(x) for x in samples)  # type: ignore[arg-type]  # no NaN


# ---------------------------------------------------------------------------
# from_counterexample
# ---------------------------------------------------------------------------


class TestFromCounterexample:
    def _make_cert(
        self, ce: dict | None, status: Status = Status.COUNTEREXAMPLE
    ) -> ProofCertificate:
        return ProofCertificate(
            function_name="test_fn",
            source_hash="abc123",
            status=status,
            preconditions=(),
            postconditions=("0 <= x",),
            counterexample=ce,
            message="test",
        )

    def test_from_counterexample_extracts_args(self) -> None:
        cert = self._make_cert({"x": -1, "y": 2, "__return__": -1})
        result = from_counterexample(cert)
        assert result == {"x": -1, "y": 2}
        assert "__return__" not in result

    def test_from_counterexample_no_return_key(self) -> None:
        cert = self._make_cert({"x": 5})
        result = from_counterexample(cert)
        assert result == {"x": 5}

    def test_from_counterexample_no_ce_raises(self) -> None:
        cert = self._make_cert(None, status=Status.VERIFIED)
        with pytest.raises(ValueError, match="no counterexample"):
            from_counterexample(cert)

    def test_from_counterexample_unknown_status_raises(self) -> None:
        cert = self._make_cert(None, status=Status.UNKNOWN)
        with pytest.raises(ValueError, match="no counterexample"):
            from_counterexample(cert)


# ---------------------------------------------------------------------------
# hypothesis_check
# ---------------------------------------------------------------------------


class TestHypothesisCheck:
    def test_hypothesis_check_passes(self) -> None:
        def double(x: Annotated[float, Ge(0.0)]) -> float:
            return x * 2

        result = hypothesis_check(
            double,
            post=lambda x, r: r >= 0.0,
            max_examples=200,
        )
        assert isinstance(result, HypothesisResult)
        assert result.passed
        assert result.counterexample is None
        assert result.examples_run > 0

    def test_hypothesis_check_finds_bug(self) -> None:
        # This function is wrong: it returns negative for strictly positive inputs
        def broken(x: Annotated[int, Ge(1), Le(100)]) -> int:
            return -x  # bug: always negates, violates r >= 0

        result = hypothesis_check(
            broken,
            post=lambda x, r: r >= 0,
            max_examples=500,
        )
        assert isinstance(result, HypothesisResult)
        assert not result.passed
        assert result.counterexample is not None
        # The counterexample must be in the valid range and violate r >= 0
        ce_x = result.counterexample["x"]
        assert isinstance(ce_x, int)
        assert broken(ce_x) < 0

    def test_hypothesis_check_with_pre(self) -> None:
        def ratio(x: int, y: int) -> float:
            return x / y

        result = hypothesis_check(
            ratio,
            pre=lambda x, y: y != 0,
            post=lambda x, y, r: isinstance(r, float),
            max_examples=200,
        )
        assert result.passed

    def test_hypothesis_check_returns_examples_run(self) -> None:
        def identity(x: Annotated[int, Ge(0), Le(10)]) -> int:
            return x

        result = hypothesis_check(identity, post=lambda x, r: r == x, max_examples=50)
        assert result.examples_run > 0


# ---------------------------------------------------------------------------
# ProofCertificate.explain()
# ---------------------------------------------------------------------------


class TestExplain:
    def _verified_cert(self, name: str = "my_func") -> ProofCertificate:
        return ProofCertificate(
            function_name=name,
            source_hash="abc123",
            status=Status.VERIFIED,
            preconditions=("x >= 0",),
            postconditions=("result >= 0",),
            solver_time_ms=1.5,
        )

    def _counterexample_cert(self) -> ProofCertificate:
        return ProofCertificate(
            function_name="bad_func",
            source_hash="def456",
            status=Status.COUNTEREXAMPLE,
            preconditions=(),
            postconditions=("0 <= result",),
            counterexample={"x": -1, "__return__": -1},
            message="Counterexample: {'x': -1, '__return__': -1}",
        )

    def test_explain_verified(self) -> None:
        cert = self._verified_cert()
        text = cert.explain()
        assert text.startswith("Q.E.D.:")
        assert "my_func" in text
        # No counterexample section
        assert "Counterexample:" not in text

    def test_explain_counterexample(self) -> None:
        cert = self._counterexample_cert()
        text = cert.explain()
        assert "COUNTEREXAMPLE" in text
        assert "bad_func" in text
        assert "Counterexample:" in text
        assert "x" in text
        assert "-1" in text
        assert "Postcondition:" in text
        assert "0 <= result" in text

    def test_explain_unknown(self) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="",
            status=Status.UNKNOWN,
            preconditions=(),
            postconditions=(),
            message="timeout",
        )
        text = cert.explain()
        assert "UNKNOWN" in text
        assert "timeout" in text

    def test_explain_no_message(self) -> None:
        cert = self._verified_cert()
        text = cert.explain()
        # Message is empty for a verified cert by default — no extra line
        lines = text.splitlines()
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# ProofCertificate.to_prompt()
# ---------------------------------------------------------------------------


class TestToPrompt:
    def _verified_cert(self, name: str = "my_func") -> ProofCertificate:
        return ProofCertificate(
            function_name=name,
            source_hash="abc123",
            status=Status.VERIFIED,
            preconditions=("x >= 0",),
            postconditions=("result >= 0",),
        )

    def _counterexample_cert(self) -> ProofCertificate:
        return ProofCertificate(
            function_name="bad_func",
            source_hash="def456",
            status=Status.COUNTEREXAMPLE,
            preconditions=(),
            postconditions=("0 <= result",),
            counterexample={"x": -1, "__return__": -1},
            message="disproved",
        )

    def test_to_prompt_verified(self) -> None:
        cert = self._verified_cert()
        text = cert.to_prompt()
        assert "VERIFIED" in text
        assert "my_func" in text
        assert "All inputs" in text

    def test_to_prompt_counterexample(self) -> None:
        cert = self._counterexample_cert()
        text = cert.to_prompt()
        assert "DISPROVED" in text
        assert "bad_func" in text
        assert "Counterexample:" in text
        assert "result=" in text
        assert "Violated:" in text
        assert "0 <= result" in text
        assert "Fix the implementation" in text

    def test_to_prompt_unknown(self) -> None:
        cert = ProofCertificate(
            function_name="hard_fn",
            source_hash="",
            status=Status.UNKNOWN,
            preconditions=(),
            postconditions=(),
            message="timeout after 5000ms",
        )
        text = cert.to_prompt()
        assert "hard_fn" in text
        assert "unknown" in text
        assert "timeout" in text

    def test_to_prompt_no_return_in_counterexample_args(self) -> None:
        cert = self._counterexample_cert()
        text = cert.to_prompt()
        # The args dict shown should not contain __return__
        assert "__return__" not in text.split("→")[0]
