"""End-to-end trust-boundary receipt tests (INT-005) on evidence-envelope/v2.

Drives the full chain — Z3 contract (provably) → SMT-LIB VC → pcc-core
re-check verdict → SP1 attestation leg → content-addressed v2 envelope —
through the ``pcc-sp1`` binary (``PCC_SP1_BIN`` env var, or ``pcc-sp1`` on
PATH). The whole module is skipped when the binary is absent so casual
``pytest`` stays green (mirrors tests/test_succinct.py).

The attestation mode is asserted against what the binary actually supports:
a guest-built binary yields ``guest-execute``; a native-only binary yields
``native-precheck-only``. The receipt never claims more than ran.
"""

import copy
import hashlib
import inspect
import os
import shutil
import textwrap
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


def _int_cert() -> tuple[Any, str]:
    """Int-theory contract Z3 verifies → VERIFIED, but outside pcc-core's
    Bool fragment. Returns the cert AND the exact source text the engine
    hashed (the bridge checks the caller-supplied source against it)."""

    def h(x: int) -> int:
        return x + 1

    # The engine hashes textwrap.dedent(inspect.getsource(h)); the bridge
    # compares against that digest, so the helper must dedent identically.
    return verify_function(h, post=lambda x, result: result > x), textwrap.dedent(
        inspect.getsource(h)
    )


def _source_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@binary
def test_accepted_bool_case_end_to_end() -> None:
    """(a) accepted Boolean case: the v2 envelope binds contract source and
    VC as inputs, PCC verdict, attestation mode, and both content addresses —
    and verifies."""
    cert, _ = _bool_tautology()
    assert cert.status == Status.VERIFIED
    source = inspect.getsource(_taut)
    receipt = build_receipt(cert, source=source)
    env = receipt["envelope"]
    payload = env["payload"]

    assert env["schema"] == "evidence-envelope/v2"
    assert env["producer"]["name"] == "pcc-sp1"

    # Contract binding: full 64-hex source digest, consistent with the
    # engine's 16-hex prefix, carried by the contract input.
    assert payload["contract"]["function_name"] == cert.function_name
    assert payload["contract"]["source_sha256"] == _source_sha(source)
    contract_input = next(i for i in env["inputs"] if i["role"] == "contract")
    assert contract_input["digest"] == f"sha256:{_source_sha(source)}"

    # VC binding: the receipt embeds the exact SMT-LIB and its hash.
    assert payload["vc"]["smt_lib"] == cert.smt_lib
    assert payload["vc"]["sha256"] == _source_sha(cert.smt_lib)
    vc_input = next(i for i in env["inputs"] if i["role"] == "verification-condition")
    assert vc_input["digest"] == f"sha256:{payload['vc']['sha256']}"
    assert vc_input["bytes"] == len(cert.smt_lib.encode("utf-8"))

    # PCC verdict: the Boolean re-checker independently confirmed unsat.
    assert payload["pcc"]["verdict"] == "unsat"
    assert env["verdict"]["status"] == "accepted"

    # SP1 leg: exactly one honest mode, consistent artifacts.
    att = payload["attestation"]
    assert att["mode"] in {"guest-execute", "native-precheck-only"}
    if att["mode"] == "guest-execute":
        assert att["public_values_sha256"] == payload["vc"]["sha256"]
    else:
        # Native-only binary: NO SP1 artifacts may appear.
        assert att["public_values_sha256"] is None
        assert att["guest_built"] is False
    assert att["proof_verified"] is None  # no proving on the fast path

    # Content addresses + explicit trust boundary.
    assert len(env["payload_sha256"]) == 64
    assert env["digest"].startswith("sha256:") and len(env["digest"]) == 7 + 64
    assert "TRUST BOUNDARY" in env["trust_boundary"]

    # The receipt re-verifies against its own bindings.
    verify_receipt(receipt)


@binary
def test_source_is_required_and_checked() -> None:
    """v2 removed the weakened 16-hex binding: the source is required, bound
    in full, and checked against the engine's own source hash."""
    cert, _ = _bool_tautology()
    source = inspect.getsource(_taut)
    assert _source_sha(source)[:16] == cert.source_hash  # sanity

    receipt = build_receipt(cert, source=source)
    env = receipt["envelope"]
    assert env["payload"]["contract"]["source_sha256"] == _source_sha(source)
    verify_receipt(receipt)

    # A stale/mismatched source text fails loudly at the bridge.
    with pytest.raises(ReceiptError, match="source"):
        build_receipt(cert, source=source + "\n")


@binary
def test_unsupported_theory_case_abstains() -> None:
    """(b) unsupported theory: Z3 VERIFIED the Int contract, but pcc-core is
    Bool-only → the receipt ABSTAINS. Never a fake accept."""
    cert, source = _int_cert()
    assert cert.status == Status.VERIFIED
    assert "Int" in cert.smt_lib

    receipt = build_receipt(cert, source=source)
    env = receipt["envelope"]
    assert env["verdict"]["status"] == "abstained"
    assert env["payload"]["pcc"]["verdict"] == "unsupported"
    assert env["payload"]["attestation"]["mode"] == "none"
    assert env["payload"]["attestation"]["proof_verified"] is None
    assert env["payload"]["attestation"]["public_values_sha256"] is None

    # An abstention is still a consistent, verifiable record.
    verify_receipt(receipt)


@binary
def test_tampered_script_case_rejected() -> None:
    """(c) tampered script: mutating the embedded VC, the status, the verdict,
    or forging a proof claim must all fail binding verification."""
    cert, _ = _bool_tautology()
    receipt = build_receipt(cert, source=inspect.getsource(_taut))
    verify_receipt(receipt)

    # Flip one byte of the embedded script: content no longer hashes.
    tampered = copy.deepcopy(receipt)
    tampered["envelope"]["payload"]["vc"]["smt_lib"] = receipt["envelope"]["payload"][
        "vc"
    ]["smt_lib"].replace("check-sat", "check-sat)", 1)
    with pytest.raises(ReceiptError):
        verify_receipt(tampered)

    # Substitute a DIFFERENT valid script: VC hash mismatch.
    _, cert_g = _bool_tautology()
    if cert_g.status == Status.VERIFIED and cert_g.smt_lib != cert.smt_lib:
        swapped = copy.deepcopy(receipt)
        swapped["envelope"]["payload"]["vc"]["smt_lib"] = cert_g.smt_lib
        with pytest.raises(ReceiptError):
            verify_receipt(swapped)

    # Upgrade an abstention to an accept: content-address mismatch.
    int_cert, int_source = _int_cert()
    abstained = build_receipt(int_cert, source=int_source)
    forged = copy.deepcopy(abstained)
    forged["envelope"]["verdict"]["status"] = "accepted"
    with pytest.raises(ReceiptError):
        verify_receipt(forged)

    # Forge a proof verification onto the fast-path attestation.
    forged2 = copy.deepcopy(receipt)
    forged2["envelope"]["payload"]["attestation"]["proof_verified"] = True
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
        build_receipt(cert, source=inspect.getsource(bad))
