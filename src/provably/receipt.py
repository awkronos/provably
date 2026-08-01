"""End-to-end trust-boundary receipts (INT-005).

Bridge a Z3-``VERIFIED`` :class:`~provably.engine.ProofCertificate` to ONE
content-addressed receipt that binds every leg of the trust boundary:

- **contract** — the verified function's name and source SHA-256,
- **vc** — the emitted SMT-LIB script (embedded verbatim) and its SHA-256,
- **pcc** — the ``pcc-core`` Boolean re-check verdict (unsat / sat /
  unsupported; unsupported theories *abstain*, never a fake accept),
- **attestation** — exactly what the SP1 leg did (``sp1-prove-verify`` /
  ``guest-execute`` / ``native-precheck-only`` / ``none``), the committed
  public values when a guest ran, and whether an SP1 proof was verified,
- **receipt_sha256** — the content address of all the above,
- **trust_boundary** — the explicit statement of what is and is not attested.

The receipt is produced and verified by the ``pcc-sp1`` binary (``receipt`` /
``receipt-verify`` subcommands; set ``PCC_SP1_BIN``, else ``pcc-sp1`` on
``PATH``). This module is a thin, fully-typed bridge; the evidence and its
verification live in the Rust receipt module so the attestation mode is
reported by the binary that actually ran it.

Example::

    from provably import verify_function
    from provably.receipt import build_receipt, verify_receipt

    def f(a: bool) -> bool:
        return a or not a

    cert = verify_function(f, post=lambda a, result: result)
    receipt = build_receipt(cert)      # status "accepted" (mode recorded)
    verify_receipt(receipt)            # re-derives every binding
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .engine import ProofCertificate

SCHEMA = "pcc-trust-boundary-receipt/1"

_VALID_STATUS = frozenset({"accepted", "abstained", "rejected"})
_VALID_MODES = frozenset(
    {"sp1-prove-verify", "guest-execute", "native-precheck-only", "none"}
)


class ReceiptError(RuntimeError):
    """Raised when the certificate carries no VC, the prover binary fails,
    or a receipt fails binding verification."""


def _bin() -> str:
    return os.environ.get("PCC_SP1_BIN", "pcc-sp1")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise ReceiptError(f"pcc-sp1 binary not found ({_bin()}): {e}") from e


def _write_tmp(text: str, suffix: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="provably-receipt-")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return Path(name)


def build_receipt(
    cert: ProofCertificate,
    *,
    source: str | None = None,
    prove: bool = False,
) -> dict[str, Any]:
    """Produce the end-to-end trust-boundary receipt for a verified contract.

    Args:
        cert: A ``VERIFIED`` :class:`ProofCertificate` carrying its SMT-LIB
            verification condition (``smt_lib``).
        source: The contract's exact source text. When given, the receipt
            binds the full 64-hex SHA-256 of the source; otherwise it binds
            the engine's 16-hex ``cert.source_hash`` prefix.
        prove: Upgrade the SP1 leg to a real proof + verify (requires a
            ``pcc-sp1`` binary built with the guest; otherwise the prover
            refuses rather than silently downgrading). Default ``False`` —
            the fast path (guest execute, or native re-check only), and the
            receipt's ``attestation.mode`` records exactly which ran.

    Returns:
        The receipt as a JSON-compatible dict (schema
        ``pcc-trust-boundary-receipt/1``).

    Raises:
        ReceiptError: If the cert is not ``VERIFIED``, carries no VC, or the
            prover binary fails. A VC outside the re-checkable Bool fragment
            is NOT an error — the receipt comes back ``abstained``.
    """
    if not cert.verified:
        raise ReceiptError(f"certificate is not VERIFIED (status={cert.status.value})")
    if not cert.smt_lib:
        raise ReceiptError("certificate carries no SMT-LIB VC (smt_lib is empty)")

    source_sha = (
        hashlib.sha256(source.encode("utf-8")).hexdigest()
        if source is not None
        else cert.source_hash
    )

    tmp = _write_tmp(cert.smt_lib, ".smt2")
    try:
        cmd = [
            _bin(),
            "receipt",
            "--script",
            str(tmp),
            "--contract-name",
            cert.function_name,
            "--contract-sha256",
            source_sha,
        ]
        if prove:
            cmd.append("--prove")
        res = _run(cmd)
    finally:
        tmp.unlink(missing_ok=True)

    if res.returncode != 0:
        raise ReceiptError(
            "pcc-sp1 receipt failed: " + (res.stderr.strip() or res.stdout.strip())
        )
    try:
        receipt: dict[str, Any] = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise ReceiptError(f"pcc-sp1 receipt emitted non-JSON output: {e}") from e

    _check_shape(receipt)
    return receipt


def _check_shape(receipt: dict[str, Any]) -> None:
    """Fail fast on a malformed receipt (full binding checks are verify_receipt's)."""
    if receipt.get("schema") != SCHEMA:
        raise ReceiptError(f"unexpected receipt schema: {receipt.get('schema')!r}")
    status = receipt.get("status")
    if status not in _VALID_STATUS:
        raise ReceiptError(f"unexpected receipt status: {status!r}")
    attestation = receipt.get("attestation")
    if not isinstance(attestation, dict) or attestation.get("mode") not in _VALID_MODES:
        mode = attestation.get("mode") if isinstance(attestation, dict) else None
        raise ReceiptError(f"unexpected attestation mode: {mode!r}")
    if status == "accepted" and attestation["mode"] == "none":
        raise ReceiptError("accepted receipt with no attestation")
    if not isinstance(receipt.get("receipt_sha256"), str):
        raise ReceiptError("receipt missing its content address")


def verify_receipt(receipt: dict[str, Any]) -> None:
    """Re-derive and check every binding in a receipt.

    Re-hashes the embedded script and the content address, re-runs the
    pcc-core re-check on the embedded VC, and enforces verdict / status /
    attestation-mode consistency. Any tamper — a flipped byte in the embedded
    script, an upgraded status, a forged proof claim — raises.

    Raises:
        ReceiptError: Listing every binding check that failed.
    """
    tmp = _write_tmp(json.dumps(receipt), ".json")
    try:
        res = _run([_bin(), "receipt-verify", "--file", str(tmp)])
    finally:
        tmp.unlink(missing_ok=True)
    if res.returncode != 0:
        raise ReceiptError(
            "receipt failed binding verification: "
            + (res.stderr.strip() or res.stdout.strip())
        )
