"""End-to-end trust-boundary receipts (INT-005) on ``evidence-envelope/v2``.

Bridge a Z3-``VERIFIED`` :class:`~provably.engine.ProofCertificate` to ONE
content-addressed v2 envelope that binds every leg of the trust boundary:

- **inputs** — the contract source (role ``contract``, full 64-hex SHA-256;
  the v1 16-hex engine-prefix binding was removed) and the verification
  condition (role ``verification-condition``),
- **payload.vc** — the emitted SMT-LIB script (embedded verbatim) and its
  SHA-256,
- **payload.pcc** — the ``pcc-core`` Boolean re-check verdict (unsat / sat /
  unsupported; unsupported theories *abstain*, never a fake accept),
- **payload.attestation** — exactly what the SP1 leg did
  (``sp1-prove-verify`` / ``guest-execute`` / ``native-precheck-only`` /
  ``none``), the committed public values when a guest ran, and whether an
  SP1 proof was verified,
- **verdict.status** — ``accepted`` / ``abstained`` / ``rejected``,
- **digest** — the envelope's content address (v2 canonical form: sorted
  keys, compact separators, UTF-8, trailing newline),
- **trust_boundary** — the explicit statement of what is and is not attested.

The receipt is produced and verified by the ``pcc-sp1`` binary (``receipt`` /
``receipt-verify`` subcommands; set ``PCC_SP1_BIN``, else ``pcc-sp1`` on
``PATH``). This module is a thin, fully-typed bridge; the evidence and its
verification live in the Rust receipt module so the attestation mode is
reported by the binary that actually ran it.

Example::

    import inspect
    from provably import verify_function
    from provably.receipt import build_receipt, verify_receipt

    def f(a: bool) -> bool:
        return a or not a

    cert = verify_function(f, post=lambda a, result: result)
    receipt = build_receipt(cert, source=inspect.getsource(f))
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

SCHEMA = "evidence-envelope/v2"

# Statuses this producer (pcc-sp1) emits — a subset of the v2 verdict enum
# (which also admits ``unavailable`` and ``recorded`` for other producers).
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
    source: str,
    prove: bool = False,
) -> dict[str, Any]:
    """Produce the end-to-end trust-boundary receipt for a verified contract.

    Args:
        cert: A ``VERIFIED`` :class:`ProofCertificate` carrying its SMT-LIB
            verification condition (``smt_lib``).
        source: The contract's exact source text (required). v2 binds the
            full 64-hex SHA-256 of the source — the v1 16-hex engine-prefix
            fallback was removed — and the bridge checks the digest against
            the engine's own ``cert.source_hash`` prefix so a stale or
            mismatched source text fails loudly.
        prove: Upgrade the SP1 leg to a real proof + verify (requires a
            ``pcc-sp1`` binary built with the guest; otherwise the prover
            refuses rather than silently downgrading). Default ``False`` —
            the fast path (guest execute, or native re-check only), and the
            receipt's ``payload.attestation.mode`` records exactly which ran.

    Returns:
        The receipt as a JSON-compatible dict: an ``evidence-envelope/v2``
        ``envelope`` plus non-addressed ``telemetry`` in the wrapper.

    Raises:
        ReceiptError: If the cert is not ``VERIFIED``, carries no VC, the
            supplied source does not match the certificate's source hash,
            or the prover binary fails. A VC outside the re-checkable Bool
            fragment is NOT an error — the receipt comes back ``abstained``.
    """
    if not cert.verified:
        raise ReceiptError(f"certificate is not VERIFIED (status={cert.status.value})")
    if not cert.smt_lib:
        raise ReceiptError("certificate carries no SMT-LIB VC (smt_lib is empty)")

    source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if not source_sha.startswith(cert.source_hash):
        raise ReceiptError(
            "supplied source does not match the certificate's source hash "
            f"(engine prefix {cert.source_hash}, full digest {source_sha})"
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
    envelope = receipt.get("envelope")
    if not isinstance(envelope, dict):
        raise ReceiptError("receipt carries no v2 envelope")
    if envelope.get("schema") != SCHEMA:
        raise ReceiptError(f"unexpected receipt schema: {envelope.get('schema')!r}")
    verdict = envelope.get("verdict")
    status = verdict.get("status") if isinstance(verdict, dict) else None
    if status not in _VALID_STATUS:
        raise ReceiptError(f"unexpected receipt status: {status!r}")
    payload = envelope.get("payload")
    attestation = payload.get("attestation") if isinstance(payload, dict) else None
    if not isinstance(attestation, dict) or attestation.get("mode") not in _VALID_MODES:
        mode = attestation.get("mode") if isinstance(attestation, dict) else None
        raise ReceiptError(f"unexpected attestation mode: {mode!r}")
    if status == "accepted" and attestation["mode"] == "none":
        raise ReceiptError("accepted receipt with no attestation")
    inputs = envelope.get("inputs")
    if (
        not isinstance(inputs, list)
        or not inputs
        or not all(
            isinstance(i, dict) and _is_qualified_digest(i.get("digest")) for i in inputs
        )
    ):
        raise ReceiptError("receipt inputs must bind sha256:<64-hex> digests")
    digest = envelope.get("digest")
    if not _is_qualified_digest(digest):
        raise ReceiptError("receipt missing its v2 content address (digest)")
    payload_sha = envelope.get("payload_sha256")
    if not (
        isinstance(payload_sha, str)
        and len(payload_sha) == 64
        and all(c in "0123456789abcdef" for c in payload_sha)
    ):
        raise ReceiptError("receipt missing its payload address (payload_sha256)")


def _is_qualified_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 7 + 64
        and all(c in "0123456789abcdef" for c in value[7:])
    )


def verify_receipt(receipt: dict[str, Any]) -> None:
    """Re-derive and check every binding in a receipt.

    Re-hashes the embedded script, the payload address, and the envelope
    digest; re-runs the pcc-core re-check on the embedded VC; and enforces
    verdict / status / attestation-mode consistency. Any tamper — a flipped
    byte in the embedded script, an upgraded status, a forged proof claim —
    raises.

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
