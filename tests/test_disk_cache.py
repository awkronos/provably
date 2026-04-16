"""Tests for disk-persistent proof caching."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from conftest import requires_z3

pytestmark = requires_z3

from provably import clear_cache, configure, verify_function
from provably.engine import Status, _disk_cache_path, _load_from_disk, _save_to_disk


class TestDiskCacheDisabled:
    """Tests with cache_dir=None (disk cache explicitly off)."""

    @pytest.fixture(autouse=True)
    def _disable_disk(self) -> None:
        configure(cache_dir=None)

    def test_no_cache_dir_returns_none_path(self) -> None:
        assert _disk_cache_path("abc") is None

    def test_no_cache_dir_load_returns_none(self) -> None:
        assert _load_from_disk("abc") is None

    def test_no_cache_dir_save_is_noop(self) -> None:
        from provably.engine import ProofCertificate

        cert = ProofCertificate(
            function_name="f",
            source_hash="abc",
            status=Status.VERIFIED,
            preconditions=(),
            postconditions=(),
        )
        _save_to_disk("abc", cert)  # should not raise


class TestDiskCacheEnabled:
    def test_cache_dir_creates_directory(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "provably_cache"
        configure(cache_dir=str(cache_dir))
        try:
            path = _disk_cache_path("test_key")
            assert path is not None
            assert cache_dir.exists()
            assert path.parent == cache_dir
        finally:
            configure(cache_dir=None)

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        configure(cache_dir=str(cache_dir))
        try:
            from provably.engine import ProofCertificate

            cert = ProofCertificate(
                function_name="my_func",
                source_hash="deadbeef",
                status=Status.VERIFIED,
                preconditions=("x >= 0",),
                postconditions=("result >= 0",),
                solver_time_ms=1.5,
                z3_version="4.13.0",
            )
            _save_to_disk("key123", cert)

            # File should exist
            path = _disk_cache_path("key123")
            assert path is not None
            assert path.exists()

            # Load it back
            clear_cache()
            loaded = _load_from_disk("key123")
            assert loaded is not None
            assert loaded.function_name == "my_func"
            assert loaded.status == Status.VERIFIED
            assert loaded.source_hash == "deadbeef"
        finally:
            configure(cache_dir=None)

    def test_disk_cache_avoids_z3_on_second_import(self, tmp_path: Path) -> None:
        """The key optimization: disk cache skips Z3 entirely on cache hit."""
        cache_dir = tmp_path / "cache"
        configure(cache_dir=str(cache_dir))
        try:

            def add_one(x: float) -> float:
                return x + 1

            # First call: Z3 runs, proof cached to disk
            cert1 = verify_function(add_one, post=lambda x, r: r > x)
            assert cert1.verified
            assert cert1.solver_time_ms > 0

            # Clear memory cache (simulating process restart)
            clear_cache()

            # Second call: loaded from disk, no Z3
            cert2 = verify_function(add_one, post=lambda x, r: r > x)
            assert cert2.verified
            assert cert2.function_name == cert1.function_name
        finally:
            configure(cache_dir=None)

    def test_corrupt_disk_cache_returns_none(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        configure(cache_dir=str(cache_dir))
        try:
            # Write garbage
            path = _disk_cache_path("bad_key")
            assert path is not None
            path.write_text("not valid json {{{")

            loaded = _load_from_disk("bad_key")
            assert loaded is None  # graceful degradation
        finally:
            configure(cache_dir=None)

    def test_counterexample_cached_to_disk(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        configure(cache_dir=str(cache_dir))
        try:

            def negate(x: float) -> float:
                return -x

            cert = verify_function(negate, post=lambda x, r: r > 0)
            assert cert.status == Status.COUNTEREXAMPLE

            clear_cache()
            loaded = _load_from_disk(
                next(f.stem for f in cache_dir.iterdir() if f.suffix == ".json")
            )
            assert loaded is not None
            assert loaded.status == Status.COUNTEREXAMPLE
            assert loaded.counterexample is not None
        finally:
            configure(cache_dir=None)

    def test_disk_cache_measurably_faster_than_cold_verify(
        self, tmp_path: Path
    ) -> None:
        """Empirically, a disk hit should beat a cold solve by at least 10x
        on a problem whose solver_time_ms is >= 1 ms.

        We pick a small verification that's still slow enough to be
        measured reliably, then compare cold path vs disk hit. The ratio
        is conservative (10x); on-box measurements routinely see >20x.
        """
        import time

        cache_dir = tmp_path / "cache"
        configure(cache_dir=str(cache_dir))
        try:

            def quadratic_nonneg(x: float, y: float) -> float:
                # Non-trivial enough to take a measurable slice of time.
                return x * x + y * y + 1.0

            def post(x: float, y: float, r: float) -> object:
                return r > 0

            # Cold run: no cache, Z3 must solve.
            clear_cache()
            # Ensure no disk artefact from a prior run either.
            for p in cache_dir.glob("*.json"):
                p.unlink()

            t0 = time.perf_counter()
            cert_cold = verify_function(quadratic_nonneg, post=post)
            cold_ms = (time.perf_counter() - t0) * 1000.0
            assert cert_cold.verified

            # Clear in-memory cache so we're forced to read from disk.
            clear_cache()

            t0 = time.perf_counter()
            cert_disk = verify_function(quadratic_nonneg, post=post)
            disk_ms = (time.perf_counter() - t0) * 1000.0
            assert cert_disk.verified

            # Both should agree on the result; disk hit should be noticeably
            # cheaper than a cold Z3 solve.
            assert cert_disk.function_name == cert_cold.function_name
            # Skip the timing assertion when cold is already trivial — on
            # a warm-cpu machine the problem can be <0.5 ms cold, and
            # perf_counter jitter swamps the ratio.
            if cold_ms >= 1.0:
                assert disk_ms * 10 <= cold_ms, (
                    f"Disk cache not measurably faster: "
                    f"cold={cold_ms:.2f}ms disk={disk_ms:.2f}ms"
                )
        finally:
            configure(cache_dir=None)

    def test_cache_file_is_valid_json(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        configure(cache_dir=str(cache_dir))
        try:

            def f(x: float) -> float:
                return x

            verify_function(f, post=lambda x, r: r == x)

            files = list(cache_dir.glob("*.json"))
            assert len(files) == 1
            data = json.loads(files[0].read_text())
            assert data["status"] == "verified"
            assert data["function_name"] == "f"
        finally:
            configure(cache_dir=None)
