"""End-to-end trust-boundary receipt tests (INT-005).

Drives the full chain — Z3 contract (provably) → SMT-LIB VC → pcc-core
re-check verdict → SP1 attestation leg → content-addressed receipt — through
the ``pcc-sp1`` binary (``PCC_SP1_BIN`` env var, or ``pcc-sp1`` on PATH). The
whole module is skipped when the binary is absent so casual ``pytest`` stays
green (mirrors tests/test_succinct.py).

The attestation mode is asserted against what the binary actually supports:
a guest-built binary yields ``guest-execute``; a native-only binary yields
``native-precheck-only``. The receipt never claims more than ran.
"""

import hashlib
import inspect
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from provably import verify_function
from provably.engine import Status
from provably.receipt import ReceiptError, build_receipt, verify_receipt

_HAS_BIN = shutil.which(os.environ.get("PCC_SP1_BIN", "pcc-sp1")) is not None or Path(
    os.environ.get("PCC_SP1_BIN", "pcc-sp1")
).exists()

binary = pytest.mark.skipif(not _HAS_BIN, reason="pcc-sp1 binary not available")


def _taut(a: bool) -> bool:
    return a or not a  # noqa: SIM221 - tautology is the test payload


def _bool_tautology() -> tuple[Any, Any]:
    """Pure-Bool contracts Z3 verifies → VERIFIED with Bool-fragment VCs."""

    def g(a: bool, b: bool) -> bool:
        return b if a else True

    cert_f = verify_function(_taut, post=lambda a, result: result)
    cert_g = verify_function(
        g, pre=lambda a, b: a, post=lambda a, b, result: result == b
    )
    return cert_f, cert_g


def _int_cert() -> Any:
    """Int-theory contract Z3 verifies → VERIFIED, but outside pcc-core's
    Bool fragment."""

    def h(x: int) -> int:
        return x + 1

    return verify_function(h, post=lambda x, result: result > x)


@binary
def test_accepted_bool_case_end_to_end() -> None:
    """(a) accepted Boolean case: receipt binds contract source, VC, PCC
    verdict, attestation mode, and public values — and verifies."""
    cert, _ = _bool_tautology()
    assert cert.status == Status.VERIFIED
    receipt = build_receipt(cert)

    # Contract binding (engine's 16-hex source prefix when source not given).
    assert receipt["contract"]["function_name"] == cert.function_name
    assert receipt["contract"]["source_sha256"] == cert.source_hash

    # VC binding: the receipt embeds the exact SMT-LIB and its hash.
    assert receipt["vc"]["smt_lib"] == cert.smt_lib
    assert receipt["vc"]["sha256"] == hashlib.sha256(
        cert.smt_lib.encode("utf-8")
    ).hexdigest()

    # PCC verdict: the Boolean re-checker independently confirmed unsat.
    assert receipt["pcc"]["verdict"] == "unsat"
    assert receipt["status"] == "accepted"

    # SP1 leg: exactly one honest mode, consistent artifacts.
    att = receipt["attestation"]
    assert att["mode"] in {"guest-execute", "native-precheck-only"}
    if att["mode"] == "guest-execute":
        assert att["public_values_sha256"] == receipt["vc"]["sha256"]
    else:
        # Native-only binary: NO SP1 artifacts may appear.
        assert att["public_values_sha256"] is None
        assert att["guest_built"] is False
    assert att["proof_verified"] is None  # no proving on the fast path

    # Content address + explicit trust boundary.
    assert len(receipt["receipt_sha256"]) == 64
    assert "TRUST BOUNDARY" in receipt["trust_boundary"]

    # The receipt re-verifies against its own bindings.
    verify_receipt(receipt)


@binary
def test_accepted_bool_case_binds_full_source_sha() -> None:
    """When the caller supplies the contract source, the receipt binds its
    full 64-hex SHA-256, consistent with the engine's prefix."""
    cert, _ = _bool_tautology()

    source = inspect.getsource(_taut)
    # Sanity: this is the same text the engine hashed (prefix match).
    assert hashlib.sha256(source.encode()).hexdigest()[:16] == cert.source_hash

    receipt = build_receipt(cert, source=source)
    assert receipt["contract"]["source_sha256"] == hashlib.sha256(
        source.encode()
    ).hexdigest()
    verify_receipt(receipt)


@binary
def test_unsupported_theory_case_abstains() -> None:
    """(b) unsupported theory: Z3 VERIFIED the Int contract, but pcc-core is
    Bool-only → the receipt ABSTAINS. Never a fake accept."""
    cert = _int_cert()
    assert cert.status == Status.VERIFIED
    assert "Int" in cert.smt_lib

    receipt = build_receipt(cert)
    assert receipt["status"] == "abstained"
    assert receipt["pcc"]["verdict"] == "unsupported"
    assert receipt["attestation"]["mode"] == "none"
    assert receipt["attestation"]["proof_verified"] is None
    assert receipt["attestation"]["public_values_sha256"] is None

    # An abstention is still a consistent, verifiable record.
    verify_receipt(receipt)


@binary
def test_tampered_script_case_rejected() -> None:
    """(c) tampered script: mutating the embedded VC, the status, the verdict,
    or forging a proof claim must all fail binding verification."""
    cert, _ = _bool_tautology()
    receipt = build_receipt(cert)
    verify_receipt(receipt)

    # Flip one byte of the embedded script: content no longer hashes.
    tampered = dict(receipt)
    tampered["vc"] = dict(receipt["vc"])
    tampered["vc"]["smt_lib"] = receipt["vc"]["smt_lib"].replace(
        "check-sat", "check-sat)", 1
    )
    with pytest.raises(ReceiptError):
        verify_receipt(tampered)

    # Substitute a DIFFERENT valid script: VC hash mismatch.
    _, cert_g = _bool_tautology()
    if cert_g.status == Status.VERIFIED and cert_g.smt_lib != cert.smt_lib:
        swapped = dict(receipt)
        swapped["vc"] = dict(receipt["vc"])
        swapped["vc"]["smt_lib"] = cert_g.smt_lib
        with pytest.raises(ReceiptError):
            verify_receipt(swapped)

    # Upgrade an abstention to an accept: content-address mismatch.
    abstained = build_receipt(_int_cert())
    forged = dict(abstained)
    forged["status"] = "accepted"
    with pytest.raises(ReceiptError):
        verify_receipt(forged)

    # Forge a proof verification onto the fast-path attestation.
    forged2 = dict(receipt)
    forged2["attestation"] = dict(receipt["attestation"])
    forged2["attestation"]["proof_verified"] = True
    with pytest.raises(ReceiptError):
        verify_receipt(forged2)


@binary
def test_receipt_requires_verified_cert() -> None:
    """A COUNTEREXAMPLE cert has no VC to attest — hard error, no receipt."""

    def bad(a: bool) -> bool:
        return a

    cert = verify_function(bad, post=lambda a, result: result)
    assert cert.status == Status.COUNTEREXAMPLE
    with pytest.raises(ReceiptError):
        build_receipt(cert)
