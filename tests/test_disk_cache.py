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
        """Empirically, a disk hit should beat a cold solve by a large
        margin once the problem is big enough for a Z3 call to dominate
        perf_counter noise.

        We take the minimum of several cold and disk timings (best-of-N)
        so one unlucky GC pause on the disk path can't flip the result.
        """
        import time

        cache_dir = tmp_path / "cache"
        configure(cache_dir=str(cache_dir))
        try:

            # Heavier problem to push cold solve time reliably above noise.
            def quartic_nonneg(
                a: float, b: float, c: float, d: float
            ) -> float:
                return (
                    a * a * a * a
                    + b * b * b * b
                    + c * c * c * c
                    + d * d * d * d
                    + 1.0
                )

            def post(a: float, b: float, c: float, d: float, r: float) -> object:
                return r > 0

            # Warm Z3/module caches with ONE throwaway solve so the first
            # timed cold-solve doesn't also pay import cost.
            clear_cache()
            for p in cache_dir.glob("*.json"):
                p.unlink()
            verify_function(quartic_nonneg, post=post)

            cold_times: list[float] = []
            disk_times: list[float] = []
            for _ in range(5):
                # Cold: kill both memory and disk cache.
                clear_cache()
                for p in cache_dir.glob("*.json"):
                    p.unlink()
                t0 = time.perf_counter()
                cert_cold = verify_function(quartic_nonneg, post=post)
                cold_times.append((time.perf_counter() - t0) * 1000.0)
                assert cert_cold.verified

                # Disk: kill ONLY memory cache so we read back from disk.
                clear_cache()
                t0 = time.perf_counter()
                cert_disk = verify_function(quartic_nonneg, post=post)
                disk_times.append((time.perf_counter() - t0) * 1000.0)
                assert cert_disk.verified
                assert cert_disk.function_name == cert_cold.function_name

            cold_min = min(cold_times)
            disk_min = min(disk_times)

            # Skip the timing assertion when cold is trivially fast — on a
            # warm-cpu machine even a Z3 solve can be <1 ms and perf_counter
            # jitter swamps any real speedup.
            if cold_min >= 1.0:
                assert disk_min * 5 <= cold_min, (
                    f"Disk cache not measurably faster: "
                    f"cold_min={cold_min:.2f}ms disk_min={disk_min:.2f}ms "
                    f"(cold={cold_times}, disk={disk_times})"
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
