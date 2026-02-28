"""pytest plugin for provably — proof assertions in CI.

Registered automatically as ``provably`` when the package is installed.

Provides:
- ``--provably-report`` CLI flag: print a proof certificate table in the
  terminal summary for all ``@verified`` functions discovered in the test suite.
- ``--provably`` CLI flag: restrict collection to tests marked with
  ``@pytest.mark.proven``.
- ``proven`` marker: tag tests that exercise formally proven functions.

Usage::

    pytest --provably-report        # run all tests + print proof table
    pytest --provably               # run only @pytest.mark.proven tests
    pytest -m proven                # same via standard -m syntax
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from provably.engine import ProofCertificate


# ---------------------------------------------------------------------------
# Plugin registration hooks
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register provably CLI options."""
    group = parser.getgroup("provably", "Provably formal verification")
    group.addoption(
        "--provably-report",
        action="store_true",
        default=False,
        help="Print a proof certificate table in the terminal summary.",
    )
    group.addoption(
        "--provably",
        action="store_true",
        default=False,
        help="Run only tests marked with @pytest.mark.proven.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the 'proven' marker so it doesn't produce an unknown-mark warning."""
    config.addinivalue_line(
        "markers",
        "proven: mark a test as exercising a formally proven function.",
    )


# ---------------------------------------------------------------------------
# Collection filter — --provably restricts to proven-marked tests
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """If --provably is set, keep only tests marked with 'proven'."""
    if not config.getoption("--provably", default=False):
        return

    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []

    for item in items:
        if item.get_closest_marker("proven") is not None:
            selected.append(item)
        else:
            deselected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected


# ---------------------------------------------------------------------------
# Terminal summary — --provably-report prints the proof table
# ---------------------------------------------------------------------------


def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Print a proof certificate table when --provably-report is active."""
    if not config.getoption("--provably-report", default=False):
        return

    certs = _collect_proof_certificates(config)
    if not certs:
        terminalreporter.write_sep("-", "provably: no @verified functions found")
        return

    terminalreporter.write_sep("=", "provably proof certificate report")

    # Column widths
    col_name = max(len("Function"), max(len(c.function_name) for c in certs))
    col_status = max(len("Status"), max(len(c.status.value) for c in certs))
    col_hash = 16

    header = (
        f"{'Function':<{col_name}}  {'Status':<{col_status}}  "
        f"{'Hash':<{col_hash}}  {'ms':>6}  Notes"
    )
    terminalreporter.write_line(header)
    terminalreporter.write_line("-" * (len(header) + 10))

    for cert in sorted(certs, key=lambda c: c.function_name):
        status_tag = "Q.E.D." if cert.verified else cert.status.value.upper()
        notes = cert.message[:60] if cert.message else ""
        if cert.counterexample:
            args = {k: v for k, v in cert.counterexample.items() if k != "__return__"}
            notes = f"counterexample: {args}"[:60]
        line = (
            f"{cert.function_name:<{col_name}}  "
            f"{status_tag:<{col_status}}  "
            f"{cert.source_hash:<{col_hash}}  "
            f"{cert.solver_time_ms:>6.1f}  "
            f"{notes}"
        )
        terminalreporter.write_line(line)

    verified_count = sum(1 for c in certs if c.verified)
    terminalreporter.write_sep(
        "-",
        f"provably: {verified_count}/{len(certs)} functions verified",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_proof_certificates(config: pytest.Config) -> list[ProofCertificate]:
    """Walk collected test modules and gather __proof__ certificates."""
    from provably.engine import ProofCertificate as PC

    certs: dict[str, PC] = {}

    # Walk all collected items from the session (if available)
    session: pytest.Session | None = getattr(config, "_provably_session", None)
    if session is not None:
        for item in session.items:
            _scan_item_for_proofs(item, certs)
        return list(certs.values())

    # Fallback: scan sys.modules for @verified functions
    import sys

    for _mod_name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        for attr in dir(mod):
            try:
                obj = getattr(mod, attr)
            except Exception:
                continue
            if callable(obj) and hasattr(obj, "__proof__"):
                proof = obj.__proof__
                if isinstance(proof, PC):
                    certs[proof.function_name] = proof

    return list(certs.values())


def _scan_item_for_proofs(item: pytest.Item, certs: dict[str, Any]) -> None:
    """Scan a single test item's module for __proof__ attributes."""
    try:
        mod = item.module  # type: ignore[attr-defined]
    except AttributeError:
        return

    from provably.engine import ProofCertificate as PC

    for attr in dir(mod):
        try:
            obj = getattr(mod, attr)
        except Exception:
            continue
        if callable(obj) and hasattr(obj, "__proof__"):
            proof = obj.__proof__
            if isinstance(proof, PC):
                certs[proof.function_name] = proof


@pytest.fixture(scope="session", autouse=True)
def _provably_session_collector(request: pytest.FixtureRequest) -> None:
    """Store the session on the config so terminal summary can find proofs."""
    request.config._provably_session = request.session  # type: ignore[attr-defined]
