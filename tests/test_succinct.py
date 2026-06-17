"""Tests for the succinct proof-carrying-certificate bridge (provably.succinct).

The `classify` tests need the `pcc-sp1` binary (PCC_SP1_BIN env var, or on
PATH); the whole module is skipped when it is absent so casual `pytest` stays
green. The real prove round-trip is CPU-heavy and additionally gated behind
PCC_SP1_SLOW=1.

The `smt_lib`-capture test needs no binary and always runs.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from provably import verify_function
from provably.engine import Status
from provably.succinct import SuccinctError, classify, prove_carrying


def _tautology_cert():
    """A function whose body is always true → VERIFIED, pure-Bool VC."""

    def f(a: bool) -> bool:
        return a or not a

    return verify_function(f, post=lambda a, result: result)


def _false_cert():
    """A function whose postcondition fails (a=False) → COUNTEREXAMPLE."""

    def f(a: bool) -> bool:
        return a

    return verify_function(f, post=lambda a, result: result)


# --- always-on: SMT-LIB capture needs no binary -----------------------------


def test_smt_lib_captured_on_verified():
    cert = _tautology_cert()
    assert cert.status == Status.VERIFIED
    assert cert.smt_lib, "VERIFIED cert should carry its unsat SMT-LIB script"
    assert "check-sat" in cert.smt_lib


def test_smt_lib_survives_json_roundtrip():
    cert = _tautology_cert()
    from provably.engine import ProofCertificate

    assert ProofCertificate.from_json(cert.to_json()).smt_lib == cert.smt_lib


# --- binary-gated: native re-check via pcc-sp1 -------------------------------

_HAS_BIN = shutil.which(os.environ.get("PCC_SP1_BIN", "pcc-sp1")) is not None or Path(
    os.environ.get("PCC_SP1_BIN", "pcc-sp1")
).exists()

binary = pytest.mark.skipif(not _HAS_BIN, reason="pcc-sp1 binary not available")


@binary
def test_classify_bool_tautology_unsat():
    verdict = classify(_tautology_cert())
    assert verdict.startswith("Unsat"), verdict


@binary
def test_classify_requires_verified():
    cert = _false_cert()
    assert cert.status == Status.COUNTEREXAMPLE
    with pytest.raises(SuccinctError):
        classify(cert)


@binary
@pytest.mark.skipif(
    os.environ.get("PCC_SP1_SLOW") != "1",
    reason="real SP1 proof is CPU-heavy; set PCC_SP1_SLOW=1 to run",
)
def test_prove_carrying_roundtrip():
    cert = _tautology_cert()
    out = Path(tempfile.gettempdir()) / "provably-py-succinct-cert.bin"
    proof = prove_carrying(cert, out)
    assert Path(proof.cert_path).exists()
    assert len(proof.vc_sha256) == 64
