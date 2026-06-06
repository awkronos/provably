"""Succinct proof-carrying certificates via SP1.

Bridge a Z3-``VERIFIED`` :class:`~provably.engine.ProofCertificate` to a
succinct SP1 proof that its verification condition's unsatisfiability re-checks
*inside the zkVM* — verifiable later with **no Z3 and no trust in this
process**. Re-checking and proving are delegated to the ``pcc-sp1`` binary
(set ``PCC_SP1_BIN``, else ``pcc-sp1`` on ``PATH``), which runs the ``pcc-core``
checker both natively and inside SP1.

Honest scope: only the **Bool fragment** is re-checkable today (see
``pcc-core``). Anything else comes back ``Unsupported`` from the prover — never
a fake proof. This mirrors the Rust ``provably::succinct`` module.

Example::

    from provably import verify_function
    from provably.succinct import classify, prove_carrying

    def f(a: bool) -> bool:
        return a or not a
    cert = verify_function(f, post=lambda a, result: result)

    classify(cert)                       # 'Unsat' — re-checked, no proof yet
    proof = prove_carrying(cert, "cert.bin")   # succinct SP1 proof on disk
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .engine import ProofCertificate


class SuccinctError(RuntimeError):
    """Raised when the certificate carries no VC, or the prover binary fails."""


@dataclass(frozen=True)
class SuccinctProof:
    """A succinct SP1 proof-carrying certificate for a verified VC."""

    vc_sha256: str  # hex SHA-256 of the SMT-LIB script the proof attests
    cert_path: str  # path to the saved SP1 proof
    backend: str = "sp1"


def _bin() -> str:
    return os.environ.get("PCC_SP1_BIN", "pcc-sp1")


def _write_vc(smt_lib: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=".smt2", prefix="provably-vc-")
    with os.fdopen(fd, "w") as f:
        f.write(smt_lib)
    return Path(name)


def _require_vc(cert: ProofCertificate) -> None:
    if not cert.verified:
        raise SuccinctError(f"certificate is not VERIFIED (status={cert.status.value})")
    if not cert.smt_lib:
        raise SuccinctError("certificate carries no SMT-LIB VC (smt_lib is empty)")


def classify(cert: ProofCertificate) -> str:
    """Native re-check of the cert's VC (no proving, fast).

    Shells to ``pcc-sp1 check`` and returns its verdict string — e.g.
    ``'Unsat'`` (re-checkable, ready to prove), ``'Sat([...])'``, or
    ``'Unsupported(...)'`` (outside the Bool fragment).

    Raises :class:`SuccinctError` if the cert is not ``VERIFIED``, carries no
    VC, or the binary is unavailable.
    """
    _require_vc(cert)
    tmp = _write_vc(cert.smt_lib)
    try:
        out = subprocess.run(
            [_bin(), "check", "--script", str(tmp)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise SuccinctError(f"pcc-sp1 binary not found ({_bin()}): {e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    if out.returncode != 0:
        raise SuccinctError(f"pcc-sp1 check failed: {out.stderr.strip()}")
    return out.stdout.strip()


def prove_carrying(cert: ProofCertificate, out_path: str | os.PathLike[str]) -> SuccinctProof:
    """Produce a succinct SP1 proof that the cert's VC is unsatisfiable.

    Shells to ``pcc-sp1 prove`` (which re-checks inside the zkVM and
    self-verifies), saving the certificate to ``out_path``.

    Raises :class:`SuccinctError` if the cert isn't ``VERIFIED``, carries no
    VC, the VC is outside the re-checkable Bool fragment, or the prover fails.
    Never returns a fake proof.
    """
    _require_vc(cert)
    out = Path(out_path)
    tmp = _write_vc(cert.smt_lib)
    try:
        res = subprocess.run(
            [_bin(), "prove", "--script", str(tmp), "--out", str(out)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise SuccinctError(f"pcc-sp1 binary not found ({_bin()}): {e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    if res.returncode != 0:
        raise SuccinctError(
            "pcc-sp1 prove failed (VC outside Bool fragment, or prover error): "
            f"{res.stderr.strip() or res.stdout.strip()}"
        )
    # Matches the digest the guest commits: sha256 of the exact script bytes.
    digest = hashlib.sha256(cert.smt_lib.encode("utf-8")).hexdigest()
    return SuccinctProof(vc_sha256=digest, cert_path=str(out))
