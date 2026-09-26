"""W26-PROV1: close the receipt.py (18%) / succinct.py (33%) zero-touch surface.

The existing tests/test_receipt.py and tests/test_succinct.py gate their
ENTIRE modules on the presence of the ``pcc-sp1`` binary — including the
pure-Python guard clauses (status checks, source-hash binding,
``_check_shape`` tamper matrix), which need no binary at all.  Where the
binary is absent (every plain ``pytest`` run, this dev host), 63/83 receipt
lines and 31/50 succinct lines have zero test touch — the exact condition
the code-map "risk" rows on the coverage-trio test files point at
("extend coverage around high-value dependencies", generation ec12384b).

These tests run ALWAYS.  Binary-dependent behavior is exercised through a
shell-script stub placed via ``PCC_SP1_BIN`` (the documented override), which
is deterministic and host-independent — never skipped on "binary missing".

Rows addressed:
  - risk 132.3 tests/test_coverage_95.py  -> receipt.py guard/shape surface
  - risk 106.4 tests/test_final_coverage.py -> succinct.py guard surface
  - risk 71.4  tests/test_coverage_boost.py -> stub-binary subprocess surface
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from provably import verify_function
from provably.engine import ProofCertificate, Status
from provably.receipt import (
    SCHEMA,
    ReceiptError,
    _bin,
    _check_shape,
    _is_qualified_digest,
    build_receipt,
    verify_receipt,
)
from provably.succinct import SuccinctError, classify, prove_carrying

# ---------------------------------------------------------------------------
# fixtures & helpers
# ---------------------------------------------------------------------------


def _taut(a: bool) -> bool:
    return a or not a  # noqa: SIM221 - tautology is the test payload


def _bad(a: bool) -> bool:
    return a


def _verified_cert() -> ProofCertificate:
    cert = verify_function(_taut, post=lambda a, result: result)
    assert cert.status == Status.VERIFIED
    assert cert.smt_lib
    return cert


def _counterexample_cert() -> ProofCertificate:
    cert = verify_function(_bad, post=lambda a, result: result)
    assert cert.status == Status.COUNTEREXAMPLE
    return cert


def _valid_receipt() -> dict[str, Any]:
    sha_a = "a" * 64
    return {
        "envelope": {
            "schema": SCHEMA,
            "verdict": {"status": "accepted"},
            "payload": {"attestation": {"mode": "guest-execute"}},
            "inputs": [{"role": "contract", "digest": f"sha256:{sha_a}"}],
            "digest": f"sha256:{sha_a}",
            "payload_sha256": "b" * 64,
        }
    }


def _stub(tmp_path: Path, body: str) -> str:
    """Install an executable pcc-sp1 stub; return its path (set via
    PCC_SP1_BIN).  ``$@`` carries the real subcommand argv."""
    p = tmp_path / "pcc-sp1-stub"
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


# ---------------------------------------------------------------------------
# _bin / _is_qualified_digest — trivial pure surface (receipt.py:70, 202)
# ---------------------------------------------------------------------------


class TestBinResolution:
    def test_default_is_pcc_sp1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PCC_SP1_BIN", raising=False)
        assert _bin() == "pcc-sp1"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PCC_SP1_BIN", "/opt/elsewhere/pcc-sp1")
        assert _bin() == "/opt/elsewhere/pcc-sp1"


class TestQualifiedDigest:
    @pytest.mark.parametrize(
        "value",
        [
            "sha256:" + "0" * 64,
            "sha256:" + "f" * 64,
            "sha256:" + "a" * 63,  # too short
            "sha256:" + "g" * 64,  # non-hex
            "5a" * 32,  # unqualified
            "",
            None,
            123,
        ],
    )
    def test_current_acceptance_table(self, value: Any) -> None:
        expected = (
            isinstance(value, str)
            and value.startswith("sha256:")
            and len(value) == 7 + 64
            and all(c in "0123456789abcdef" for c in value[7:])
        )
        assert _is_qualified_digest(value) is expected


# ---------------------------------------------------------------------------
# build_receipt guards — run BEFORE any subprocess (receipt.py:119-129)
# ---------------------------------------------------------------------------


class TestBuildReceiptGuards:
    def test_requires_verified_cert(self) -> None:
        cert = _counterexample_cert()
        with pytest.raises(ReceiptError, match="not VERIFIED"):
            build_receipt(cert, source=inspect.getsource(_bad))

    def test_requires_nonempty_smt_lib(self) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="0" * 16,
            status=Status.VERIFIED,
            preconditions=(),
            postconditions=(),
            smt_lib="",
        )
        with pytest.raises(ReceiptError, match="no SMT-LIB VC"):
            build_receipt(cert, source="")

    def test_source_hash_binding_fails_loudly(self) -> None:
        cert = _verified_cert()
        with pytest.raises(ReceiptError, match="does not match"):
            build_receipt(cert, source="# not the certified source\n")

    def test_guards_fire_without_any_binary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A guard regression that reorders the subprocess ahead of the
        # checks would hit this nonexistent path and surface as an
        # error about a binary instead of about the certificate.
        monkeypatch.setenv("PCC_SP1_BIN", str(Path("/") / "definitely" / "absent"))
        with pytest.raises(ReceiptError, match="not VERIFIED"):
            build_receipt(_counterexample_cert(), source=inspect.getsource(_bad))


# ---------------------------------------------------------------------------
# _check_shape — the tamper matrix (receipt.py:164-198), pure function,
# previously only reachable through the binary-gated e2e tests.
# ---------------------------------------------------------------------------


class TestCheckShape:
    def test_valid_receipt_passes(self) -> None:
        _check_shape(_valid_receipt())  # must not raise

    def _mangle(self, fn) -> dict[str, Any]:
        r = _valid_receipt()
        fn(r)
        return r

    @pytest.mark.parametrize(
        "mutate, msg",
        [
            (lambda e: e.pop("envelope"), "no v2 envelope"),
            (lambda e: e["envelope"].__setitem__("schema", "evidence-envelope/v1"),
             "unexpected receipt schema"),
            (lambda e: e["envelope"]["verdict"].__setitem__("status", "unavailable"),
             "unexpected receipt status"),
            (lambda e: e["envelope"]["verdict"].__setitem__("status", "accepted") or
             e["envelope"]["payload"].__setitem__("attestation", {"mode": "forged"}),
             "unexpected attestation mode"),
            (lambda e: e["envelope"]["payload"].__setitem__("attestation", {"mode": "none"}),
             "accepted receipt with no attestation"),
            (lambda e: e["envelope"].__setitem__("inputs", []),
             "must bind sha256:<64-hex> digests"),
            (lambda e: e["envelope"].__setitem__(
                "inputs", [{"role": "contract", "digest": "md5:" + "0" * 32}]),
             "must bind sha256:<64-hex> digests"),
            (lambda e: e["envelope"].pop("digest"), "missing its v2 content address"),
            (lambda e: e["envelope"].__setitem__("payload_sha256", "zz"),
             "missing its payload address"),
        ],
    )
    def test_malformed_rejected(self, mutate, msg: str) -> None:
        with pytest.raises(ReceiptError, match=msg):
            _check_shape(self._mangle(mutate))

    def test_accepted_with_no_attestation_rejected(self) -> None:
        r = _valid_receipt()
        r["envelope"]["payload"]["attestation"] = {"mode": "none"}
        # 'none' is a VALID mode (abstain), but an ACCEPTED verdict with it
        # is the forged-claim shape line 178-179 refuses:
        with pytest.raises(ReceiptError, match="accepted receipt with no attestation"):
            _check_shape(r)

    def test_missing_payload_key_degrades_to_mode_error(self) -> None:
        r = _valid_receipt()
        r["envelope"].pop("payload")
        with pytest.raises(ReceiptError, match="unexpected attestation mode"):
            _check_shape(r)

    def test_missing_verdict_key_degrades_to_status_error(self) -> None:
        r = _valid_receipt()
        r["envelope"].pop("verdict")
        with pytest.raises(ReceiptError, match="unexpected receipt status"):
            _check_shape(r)


# ---------------------------------------------------------------------------
# build_receipt / verify_receipt subprocess legs via stub binary
# (receipt.py:131-159, 222-228)
# ---------------------------------------------------------------------------


class TestBuildReceiptStubbedBinary:
    def test_missing_binary_raises_receipt_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PCC_SP1_BIN", str(tmp_path / "absent"))
        cert = _verified_cert()
        with pytest.raises(ReceiptError, match="not found"):
            build_receipt(cert, source=inspect.getsource(_taut))

    def test_nonzero_exit_surfaced(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stub = _stub(tmp_path, "echo 'prover exploded' >&2\nexit 3\n")
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        cert = _verified_cert()
        with pytest.raises(ReceiptError, match="prover exploded"):
            build_receipt(cert, source=inspect.getsource(_taut))

    def test_non_json_output_surfaced(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stub = _stub(tmp_path, "echo 'not json at all'\n")
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        cert = _verified_cert()
        with pytest.raises(ReceiptError, match="non-JSON"):
            build_receipt(cert, source=inspect.getsource(_taut))

    def test_happy_path_binds_contract_sha_and_checks_shape(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        receipt = _valid_receipt()
        argv_file = tmp_path / "argv.txt"
        stub = _stub(
            tmp_path,
            f'printf "%s\\n" "$@" > {argv_file}\ncat <<\'EOF\'\n'
            + json.dumps(receipt)
            + "\nEOF\n",
        )
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        cert = _verified_cert()
        source = inspect.getsource(_taut)
        out = build_receipt(cert, source=source)
        assert out == receipt
        argv = argv_file.read_text().splitlines()
        assert argv[0] == "receipt"
        assert argv[1] == "--script"
        assert Path(argv[2]).exists() is False  # tmp VC unlinked after run
        assert argv[3:] == [
            "--contract-name",
            cert.function_name,
            "--contract-sha256",
            hashlib.sha256(source.encode("utf-8")).hexdigest(),
        ]
        # The script content the stub received was the cert's VC:
        # (re-donw by re-running with a capturing stub below)

    def test_script_arg_carries_the_smt_lib(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured = tmp_path / "vc.smt2"
        receipt = _valid_receipt()
        stub = _stub(
            tmp_path,
            f'cp "$3" {captured}\ncat <<\'EOF\'\n' + json.dumps(receipt) + "\nEOF\n",
        )
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        cert = _verified_cert()
        build_receipt(cert, source=inspect.getsource(_taut))
        assert captured.read_text() == cert.smt_lib


class TestVerifyReceiptStubbedBinary:
    def test_zero_exit_passes(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        stub = _stub(tmp_path, "exit 0\n")
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        verify_receipt(_valid_receipt())

    def test_nonzero_exit_raises_with_stderr(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stub = _stub(tmp_path, "echo 'digest mismatch' >&2\nexit 1\n")
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        with pytest.raises(ReceiptError, match="failed binding verification.*digest mismatch"):
            verify_receipt(_valid_receipt())

    def test_missing_binary_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PCC_SP1_BIN", str(tmp_path / "absent"))
        with pytest.raises(ReceiptError, match="not found"):
            verify_receipt(_valid_receipt())


# ---------------------------------------------------------------------------
# succinct.py guards + stub legs (succinct.py:64-67, 80-95, 108-129)
# ---------------------------------------------------------------------------


class TestSuccinctGuards:
    def test_classify_requires_verified(self) -> None:
        with pytest.raises(SuccinctError, match="not VERIFIED"):
            classify(_counterexample_cert())

    def test_prove_carrying_requires_verified(self, tmp_path: Path) -> None:
        with pytest.raises(SuccinctError, match="not VERIFIED"):
            prove_carrying(_counterexample_cert(), tmp_path / "out.bin")

    @pytest.mark.parametrize("fn", ["classify", "prove_carrying"])
    def test_requires_smt_lib(self, fn: str, tmp_path: Path) -> None:
        cert = ProofCertificate(
            function_name="f",
            source_hash="0" * 16,
            status=Status.VERIFIED,
            preconditions=(),
            postconditions=(),
            smt_lib="",
        )
        with pytest.raises(SuccinctError, match="no SMT-LIB VC"):
            if fn == "classify":
                classify(cert)
            else:
                prove_carrying(cert, tmp_path / "out.bin")

    def test_guards_fire_with_no_binary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PCC_SP1_BIN", "/definitely/absent")
        with pytest.raises(SuccinctError, match="not VERIFIED"):
            classify(_counterexample_cert())


class TestSuccinctStubbedBinary:
    def test_classify_returns_verdict_string(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stub = _stub(tmp_path, "echo 'Unsat'\n")
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        assert classify(_verified_cert()) == "Unsat"

    def test_classify_passes_check_subcommand_and_script(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured = tmp_path / "vc.smt2"
        stub = _stub(tmp_path, f'cp "$3" {captured}\necho Unsat\n')
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        cert = _verified_cert()
        classify(cert)
        assert captured.read_text() == cert.smt_lib

    def test_classify_nonzero_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stub = _stub(tmp_path, "echo 'bad script' >&2\nexit 1\n")
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        with pytest.raises(SuccinctError, match="check failed: bad script"):
            classify(_verified_cert())

    def test_classify_missing_binary_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PCC_SP1_BIN", str(tmp_path / "absent"))
        with pytest.raises(SuccinctError, match="not found"):
            classify(_verified_cert())

    def test_prove_carrying_writes_proof_and_digests_vc(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out = tmp_path / "proof.bin"
        stub = _stub(tmp_path, 'printf "SP1PROOF" > "$5"\n')
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        cert = _verified_cert()
        proof = prove_carrying(cert, out)
        assert proof.cert_path == str(out)
        assert out.read_text() == "SP1PROOF"
        assert proof.vc_sha256 == hashlib.sha256(cert.smt_lib.encode("utf-8")).hexdigest()
        assert proof.backend == "sp1"

    def test_prove_carrying_nonzero_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stub = _stub(tmp_path, "echo 'outside Bool fragment' >&2\nexit 2\n")
        monkeypatch.setenv("PCC_SP1_BIN", stub)
        with pytest.raises(SuccinctError, match="outside Bool fragment"):
            prove_carrying(_verified_cert(), tmp_path / "proof.bin")

    def test_prove_carrying_missing_binary_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PCC_SP1_BIN", str(tmp_path / "absent"))
        with pytest.raises(SuccinctError, match="not found"):
            prove_carrying(_verified_cert(), tmp_path / "proof.bin")


class TestSuccinctErrorTypeContract:
    """Both bridges' errors stay RuntimeError subclasses (callers catch
    RuntimeError, not Exception) — characterization."""

    def test_receipt_error_is_runtime_error(self) -> None:
        assert issubclass(ReceiptError, RuntimeError)

    def test_succinct_error_is_runtime_error(self) -> None:
        assert issubclass(SuccinctError, RuntimeError)


def test_os_environ_default_untouched() -> None:
    """Characterize that these tests never leak PCC_SP1_BIN (monkeypatch
    auto-undoes; a manual os.environ write here would poison the binary-
    gated e2e modules' _HAS_BIN detection)."""
    assert "PCC_SP1_BIN" not in os.environ
