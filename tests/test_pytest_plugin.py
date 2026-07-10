"""Tests for provably.pytest_plugin using pytester."""

from __future__ import annotations

import pytest

# Enable the pytester built-in plugin (required to use the pytester fixture)
pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def _pin_asyncio_fixture_loop_scope(pytester: pytest.Pytester) -> None:
    """Give nested pytester runs an explicit asyncio fixture loop scope.

    pytester executes in a fresh tmp dir with no config file, so pytest-asyncio
    emits its "asyncio_default_fixture_loop_scope is unset" deprecation warning
    inside every nested run. Pin it the same way the real pyproject.toml does.
    """
    pytester.makeini("[pytest]\nasyncio_default_fixture_loop_scope = function\n")


@pytest.fixture(autouse=True)
def _isolate_nested_pytest_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep nested ``pytester.runpytest()`` sessions hermetic.

    By default a nested pytest session re-scans every installed
    distribution's ``pytest11`` entry points, including unrelated plugins
    from other projects that happen to share this interpreter (e.g.
    ``pytest-playwright`` on a shared/self-hosted CI Python). That plugin
    installs a ``pytest_runtest_call`` hookwrapper around
    ``playwright._impl._assertions._soft_scope()``, which is a
    process-global, non-reentrant context manager
    (``assert _soft_errors is None, "nested soft assertion scopes are not
    supported"``). When the *outer* test here is itself running inside that
    hookwrapper and starts a nested pytest session that also autoloads
    ``pytest-playwright``, the nested session's attempt to enter
    ``_soft_scope()`` again collides with the still-open outer scope and
    fails every test in the nested run.

    Disabling autoload avoids that (and any similar) ambient-plugin
    collision; the ``provably`` plugin under test is re-added explicitly via
    ``-p`` in each ``runpytest()`` call below.
    """
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


# ---------------------------------------------------------------------------
# --provably-report flag
# ---------------------------------------------------------------------------


class TestProvablyReportFlag:
    def test_provably_report_flag(self, pytester: pytest.Pytester) -> None:
        """--provably-report prints a proof certificate table in terminal output."""
        pytester.makepyfile(
            """
            from provably import verified
            from typing import Annotated
            from provably.types import Ge

            @verified
            def double(x: Annotated[float, Ge(0)]) -> Annotated[float, Ge(0)]:
                return x * 2

            def test_double_works():
                assert double(3.0) == 6.0
            """
        )
        result = pytester.runpytest("-p", "provably.pytest_plugin", "--provably-report", "-v")
        result.assert_outcomes(passed=1)
        # The report section header should appear
        result.stdout.fnmatch_lines(["*provably proof certificate report*"])
        # The function name should appear in the report
        result.stdout.fnmatch_lines(["*double*"])

    def test_no_report_without_flag(self, pytester: pytest.Pytester) -> None:
        """Without --provably-report, no table is printed."""
        pytester.makepyfile(
            """
            from provably import verified
            from typing import Annotated
            from provably.types import Ge

            @verified
            def triple(x: Annotated[float, Ge(0)]) -> Annotated[float, Ge(0)]:
                return x * 3

            def test_triple_works():
                assert triple(2.0) == 6.0
            """
        )
        result = pytester.runpytest("-p", "provably.pytest_plugin", "-v")
        result.assert_outcomes(passed=1)
        # Report header should NOT appear
        assert "provably proof certificate report" not in result.stdout.str()

    def test_provably_report_no_verified_functions(self, pytester: pytest.Pytester) -> None:
        """Report with no @verified functions shows 'no @verified functions found'."""
        pytester.makepyfile(
            """
            def test_plain():
                assert 1 + 1 == 2
            """
        )
        result = pytester.runpytest("-p", "provably.pytest_plugin", "--provably-report", "-v")
        result.assert_outcomes(passed=1)
        result.stdout.fnmatch_lines(["*provably: no @verified functions found*"])


# ---------------------------------------------------------------------------
# proven marker
# ---------------------------------------------------------------------------


class TestProvenMarker:
    def test_proven_marker(self, pytester: pytest.Pytester) -> None:
        """@pytest.mark.proven test is collected and runs normally."""
        pytester.makepyfile(
            """
            import pytest
            from provably import verified
            from typing import Annotated
            from provably.types import Ge

            @verified
            def nonneg_double(x: Annotated[float, Ge(0)]) -> Annotated[float, Ge(0)]:
                return x * 2

            @pytest.mark.proven
            def test_nonneg_double_is_verified():
                assert nonneg_double.__proof__.verified

            def test_ordinary():
                assert 2 + 2 == 4
            """
        )
        result = pytester.runpytest("-p", "provably.pytest_plugin", "-v")
        result.assert_outcomes(passed=2)
        result.stdout.fnmatch_lines(["*test_nonneg_double_is_verified*PASSED*"])

    def test_provably_flag_filters_to_proven(self, pytester: pytest.Pytester) -> None:
        """--provably runs only proven-marked tests."""
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.proven
            def test_proven_one():
                assert True

            def test_not_proven():
                assert True
            """
        )
        result = pytester.runpytest("-p", "provably.pytest_plugin", "--provably", "-v")
        result.assert_outcomes(passed=1)
        result.stdout.fnmatch_lines(["*test_proven_one*PASSED*"])
        assert "test_not_proven" not in result.stdout.str()

    def test_proven_marker_no_warning(self, pytester: pytest.Pytester) -> None:
        """Using @pytest.mark.proven does not produce an unknown-mark warning."""
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.proven
            def test_clean():
                assert True
            """
        )
        result = pytester.runpytest(
            "-p", "provably.pytest_plugin", "-v", "-W", "error::pytest.PytestUnknownMarkWarning"
        )
        result.assert_outcomes(passed=1)
