"""Tests for the succinct proof-carrying-certificate bridge (provably.succinct).

The native `classify` tests need the `pcc-sp1` binary (PCC_SP1_BIN env var,
or on PATH) and are skipped when it is absent. The real prove round-trip is
CPU-heavy and additionally gated behind PCC_SP1_SLOW=1.

SMT-LIB capture and wrapper artifact tests need no SP1 binary and always run.
"""

import hashlib
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
        return a or not a  # noqa: SIM221 - tautology is the test payload for the verifier

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

_HAS_BIN = (
    shutil.which(os.environ.get("PCC_SP1_BIN", "pcc-sp1")) is not None
    or Path(os.environ.get("PCC_SP1_BIN", "pcc-sp1")).exists()
)

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


def _stub_prover(monkeypatch, tmp_path, body):
    """Exercise process/artifact handling, without claiming a real SP1 proof."""
    prover = tmp_path / "prover"
    prover.write_text("#!/bin/sh\n" + body)
    prover.chmod(0o700)
    monkeypatch.setenv("PCC_SP1_BIN", str(prover))
    return prover


@pytest.mark.parametrize("stale", [False, True])
def test_prove_rejects_success_without_fresh_artifact(monkeypatch, tmp_path, stale):
    _stub_prover(monkeypatch, tmp_path, "exit 0\n")
    out = tmp_path / "proof.bin"
    if stale:
        out.write_bytes(b"old proof")
    with pytest.raises(SuccinctError, match="artifact"):
        prove_carrying(_tautology_cert(), out)
    assert not out.exists()


@pytest.mark.parametrize("kind", ["empty", "symlink", "directory"])
def test_prove_rejects_invalid_artifact(monkeypatch, tmp_path, kind):
    body = {
        "empty": ': > "$5"\n',
        "symlink": 'ln -s "$0" "$5"\n',
        "directory": 'mkdir "$5"\n',
    }[kind]
    prover = _stub_prover(monkeypatch, tmp_path, body)
    out = tmp_path / "proof.bin"
    with pytest.raises(SuccinctError, match="empty|regular"):
        prove_carrying(_tautology_cert(), out)
    assert prover.read_text() == "#!/bin/sh\n" + body
    assert out.is_dir() if kind == "directory" else not out.exists()


def test_prove_binds_exact_fresh_artifact(monkeypatch, tmp_path):
    _stub_prover(monkeypatch, tmp_path, 'printf "fresh artifact" > "$5"\n')
    out = tmp_path / "proof.bin"
    out.write_bytes(b"stale")
    cert = _tautology_cert()
    proof = prove_carrying(cert, out)
    assert proof.vc_sha256 == hashlib.sha256(cert.smt_lib.encode()).hexdigest()
    assert proof.artifact_sha256 == hashlib.sha256(b"fresh artifact").hexdigest()
    assert proof.artifact_len == len(b"fresh artifact")
    assert out.read_bytes() == b"fresh artifact"


def test_prove_removes_partial_artifact_on_failure(monkeypatch, tmp_path):
    _stub_prover(monkeypatch, tmp_path, 'printf "partial" > "$5"\nexit 1\n')
    out = tmp_path / "proof.bin"
    with pytest.raises(SuccinctError, match="prove failed"):
        prove_carrying(_tautology_cert(), out)
    assert not out.exists()


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink", "path"])
def test_prove_preserves_prover_alias(monkeypatch, tmp_path, alias):
    prover = _stub_prover(monkeypatch, tmp_path, "exit 0\n")
    out = tmp_path / "proof.bin"
    if alias == "symlink":
        out.symlink_to(prover)
    elif alias == "hardlink":
        os.link(prover, out)
    else:
        out = prover
    if alias == "path":
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.setenv("PCC_SP1_BIN", prover.name)
    with pytest.raises(SuccinctError, match="aliases prover"):
        prove_carrying(_tautology_cert(), out)
    assert prover.read_text() == "#!/bin/sh\nexit 0\n"


def test_prove_cleans_stale_artifact_when_binary_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("PCC_SP1_BIN", str(tmp_path / "absent"))
    out = tmp_path / "proof.bin"
    out.write_bytes(b"stale")
    with pytest.raises(SuccinctError, match="not found"):
        prove_carrying(_tautology_cert(), out)
    assert not out.exists()
