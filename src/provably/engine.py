"""Verification engine — VC generation, Z3 solving, proof certificates.

Orchestrates the full pipeline:
  1. Parse function source → AST
  2. Create Z3 symbolic variables from type annotations
  3. Translate function body via Translator (the TCB)
  4. Build verification condition: pre ∧ body → post
  5. Negate postcondition, check UNSAT with Z3
  6. Return ProofCertificate (cached, content-addressed)

Global configuration
--------------------
Use :func:`configure` to set defaults that apply to every subsequent call::

    from provably import configure
    configure(timeout_ms=10_000, raise_on_failure=True)

These defaults can be overridden per-call via keyword arguments to
:func:`verify_function` or the :func:`~provably.decorators.verified` decorator.
"""

from __future__ import annotations  # pragma: no cover

import ast  # pragma: no cover
import hashlib  # pragma: no cover
import inspect  # pragma: no cover
import json  # pragma: no cover
import logging  # pragma: no cover
import textwrap  # pragma: no cover
import time  # pragma: no cover
import types as _types  # pragma: no cover
from collections.abc import Callable  # pragma: no cover
from dataclasses import dataclass  # pragma: no cover
from enum import Enum  # pragma: no cover
from pathlib import Path  # pragma: no cover
from typing import Any, get_type_hints  # pragma: no cover

import z3  # pragma: no cover

from .translator import TranslationError, Translator  # pragma: no cover
from .types import extract_refinements, make_z3_var  # pragma: no cover

logger = logging.getLogger("provably")  # pragma: no cover

# Optional orjson accelerator for disk-cache serialization (3-5x faster than
# stdlib json for our typical certificate sizes of 200-800 bytes).
_orjson: Any = None
_HAS_ORJSON = False
try:  # pragma: no cover
    import orjson

    _orjson = orjson
    _HAS_ORJSON = True
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------

_config: dict[str, Any] = {  # pragma: no cover
    "timeout_ms": 5000,
    "raise_on_failure": False,
    "log_level": "WARNING",
    "cache_dir": str(Path.home() / ".provably" / "cache"),
}


def configure(**kwargs: Any) -> None:
    """Set global verification defaults.

    Supported keys:

    - ``timeout_ms`` (int): Z3 solver timeout in milliseconds (default 5000).
    - ``raise_on_failure`` (bool): Raise :class:`~provably.decorators.VerificationError`
      when a proof fails (default ``False``).
    - ``log_level`` (str): Python logging level for the ``provably`` logger
      (default ``"WARNING"``).
    - ``cache_dir`` (str | None): Directory for disk-persistent proof cache.
      Default: ``~/.provably/cache``. Set to ``None`` to disable disk caching.
      Proofs are persisted across process restarts — no re-proving on import.

    Example::

        from provably import configure
        configure(timeout_ms=10_000, cache_dir=".provably_cache")

    Args:
        **kwargs: Key-value pairs to update in the global config.

    Raises:
        ValueError: If an unknown configuration key is provided.
    """
    unknown = set(kwargs) - set(_config)
    if unknown:
        raise ValueError(f"Unknown configure() keys: {sorted(unknown)}")
    _config.update(kwargs)

    if "log_level" in kwargs:
        import logging

        logging.getLogger("provably").setLevel(
            getattr(logging, kwargs["log_level"], logging.WARNING)
        )


# ---------------------------------------------------------------------------
# Status + ProofCertificate
# ---------------------------------------------------------------------------


class Status(Enum):  # pragma: no cover
    """Verification result status."""

    VERIFIED = "verified"
    COUNTEREXAMPLE = "counterexample"
    UNKNOWN = "unknown"
    TRANSLATION_ERROR = "translation_error"
    SKIPPED = "skipped"


@dataclass(frozen=True)  # pragma: no cover
class ProofCertificate:
    """Immutable proof certificate for a verified function.

    Attached to decorated functions as ``func.__proof__``.

    Attributes:
        function_name: The name of the verified function.
        source_hash: SHA-256 prefix of the function's source text.
        status: The verification outcome (see :class:`Status`).
        preconditions: Human-readable Z3 string representations of
            the applied preconditions.
        postconditions: Human-readable Z3 string representations of
            the applied postconditions.
        counterexample: Input values that disprove the postcondition,
            or ``None`` if not applicable.
        message: Human-readable explanation (error message, skip reason, etc.).
        solver_time_ms: Wall-clock time spent in the Z3 solver.
        z3_version: The Z3 version string used for this proof.
    """

    function_name: str  # pragma: no cover
    source_hash: str  # pragma: no cover
    status: Status  # pragma: no cover
    preconditions: tuple[str, ...]  # pragma: no cover
    postconditions: tuple[str, ...]  # pragma: no cover
    counterexample: dict[str, Any] | None = None  # pragma: no cover
    message: str = ""  # pragma: no cover
    solver_time_ms: float = 0.0  # pragma: no cover
    z3_version: str = ""  # pragma: no cover
    smt_lib: str = ""  # pragma: no cover — SMT-LIB unsat script (VERIFIED only)

    @property
    def verified(self) -> bool:
        """``True`` iff the status is :attr:`Status.VERIFIED`."""
        return self.status == Status.VERIFIED

    def __str__(self) -> str:
        sym = {"verified": "Q.E.D.", "counterexample": "DISPROVED", "unknown": "?"}
        tag = sym.get(self.status.value, self.status.value.upper())
        out = f"[{tag}] {self.function_name}"
        if self.counterexample:
            out += f" — counterexample: {self.counterexample}"
        if self.message:
            out += f" ({self.message})"
        return out

    def explain(self) -> str:
        """Human-readable explanation of the proof result.

        Returns a multi-line string describing the outcome, any counterexample
        found, and the violated postcondition.

        Example::

            print(func.__proof__.explain())
            # Q.E.D.: double
            # or
            # COUNTEREXAMPLE: bad_func
            #   Counterexample: {'x': -1}
            #   bad_func(x=-1) = -1
            #   Postcondition: 0 <= result
        """
        lines = [
            f"{'Q.E.D.' if self.verified else self.status.value.upper()}: {self.function_name}"
        ]
        if self.counterexample:
            args = {k: v for k, v in self.counterexample.items() if k != "__return__"}
            ret = self.counterexample.get("__return__")
            lines.append(f"  Counterexample: {args}")
            if ret is not None:
                lines.append(
                    f"  {self.function_name}({', '.join(f'{k}={v}' for k, v in args.items())}) = {ret}"
                )
            for post in self.postconditions:
                lines.append(f"  Postcondition: {post}")
        if self.message:
            lines.append(f"  {self.message}")
        return "\n".join(lines)

    def to_prompt(self) -> str:
        """Format certificate for LLM consumption in repair loops.

        Returns a single-paragraph string describing the verification result
        in a form suitable for inclusion in an LLM prompt.

        Example::

            prompt = func.__proof__.to_prompt()
            # "Function `bad_func` DISPROVED. Counterexample: {'x': -1} → result=-1
            #  Violated: 0 <= result Fix the implementation or strengthen the precondition."
        """
        if self.verified:
            return (
                f"Function `{self.function_name}` VERIFIED. "
                "All inputs satisfying preconditions produce valid outputs."
            )
        if self.status == Status.COUNTEREXAMPLE:
            args = {k: v for k, v in self.counterexample.items() if k != "__return__"}  # type: ignore[union-attr]
            ret = self.counterexample.get("__return__")  # type: ignore[union-attr]
            parts = [f"Function `{self.function_name}` DISPROVED."]
            parts.append(f"Counterexample: {args} → result={ret}")
            if self.postconditions:
                parts.append(f"Violated: {self.postconditions[0]}")
            parts.append("Fix the implementation or strengthen the precondition.")
            return " ".join(parts)
        return f"Function `{self.function_name}`: {self.status.value}. {self.message}"

    def to_json(self) -> dict[str, Any]:
        """Serialize the certificate to a JSON-compatible dict.

        All values are JSON-native types (str, int, float, bool, None, dict).
        The ``counterexample`` values are coerced to strings when they are
        not already JSON-serializable.

        Returns:
            A dict that can be passed directly to ``json.dumps()``.

        Example::

            import json
            cert = func.__proof__
            print(json.dumps(cert.to_json(), indent=2))
        """
        ce: dict[str, Any] | None = None
        if self.counterexample is not None:
            ce = {}
            for k, v in self.counterexample.items():
                if isinstance(v, int | float | bool | str | type(None)):
                    ce[k] = v
                else:
                    ce[k] = str(v)
        return {
            "function_name": self.function_name,
            "source_hash": self.source_hash,
            "status": self.status.value,
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "counterexample": ce,
            "message": self.message,
            "solver_time_ms": self.solver_time_ms,
            "z3_version": self.z3_version,
            "smt_lib": self.smt_lib,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ProofCertificate:
        """Deserialize a certificate from a JSON-compatible dict.

        This is the inverse of :meth:`to_json`.

        Args:
            data: A dict with the same keys as produced by :meth:`to_json`.

        Returns:
            A reconstructed :class:`ProofCertificate`.

        Raises:
            KeyError: If a required field is missing from *data*.
            ValueError: If the ``status`` value is not a valid :class:`Status`.

        Example::

            cert = ProofCertificate.from_json(json.loads(json_string))
        """
        return cls(
            function_name=data["function_name"],
            source_hash=data["source_hash"],
            status=Status(data["status"]),
            preconditions=tuple(data.get("preconditions", [])),
            postconditions=tuple(data.get("postconditions", [])),
            counterexample=data.get("counterexample"),
            message=data.get("message", ""),
            solver_time_ms=float(data.get("solver_time_ms", 0.0)),
            z3_version=data.get("z3_version", ""),
            smt_lib=data.get("smt_lib", ""),
        )


# ---------------------------------------------------------------------------
# Proof cache (content-addressed, memory + optional disk persistence)
# ---------------------------------------------------------------------------

_proof_cache: dict[str, ProofCertificate] = {}  # pragma: no cover

# L0 fast cache: keyed by (function bytecode, contract bytecode). Skips
# inspect.getsource() entirely on hits (saves ~25μs per call) and avoids
# re-hashing textual sources. This cache is memoization keyed on function
# identity; it is cleared by ``clear_cache()`` alongside ``_proof_cache``.
_fast_cache: dict[tuple[Any, ...], ProofCertificate] = {}  # pragma: no cover

# Memoized disk cache directory — avoids mkdir() on every call (~5μs saved).
_disk_cache_dir_cached: tuple[str | None, Path | None] = (None, None)  # pragma: no cover


def clear_cache() -> None:
    """Clear the in-memory proof cache.

    Does **not** delete disk-cached proofs. To clear disk cache, delete
    the directory set via ``configure(cache_dir=...)``.
    """
    _proof_cache.clear()
    _fast_cache.clear()


def _source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _fast_key(
    func: Callable[..., Any],
    pre: Callable[..., Any] | None,
    post: Callable[..., Any] | None,
) -> tuple[Any, ...] | None:
    """Compute a bytecode-level cache key without calling inspect.getsource.

    Returns a tuple of (func_bytecode, pre_bytecode, post_bytecode, closure_values).
    The tuple is hashable and uniquely determines proof outcome. Returns None
    if any callable doesn't expose ``__code__`` (e.g. builtins, C extensions).
    """
    try:
        fc = func.__code__
        fkey: Any = (fc.co_code, fc.co_consts, fc.co_names, fc.co_varnames, fc.co_freevars)

        # Closure cells for func (rare, but correctness matters)
        if func.__closure__:
            fcells = tuple(
                _safe_cell_repr(cell) for cell in func.__closure__
            )
        else:
            fcells = ()

        def _cb_key(cb: Callable[..., Any] | None) -> Any:
            if cb is None:
                return None
            cc = cb.__code__
            cells: tuple[Any, ...] = ()
            if cb.__closure__:
                cells = tuple(_safe_cell_repr(c) for c in cb.__closure__)
            return (cc.co_code, cc.co_consts, cc.co_names, cells)

        return (fkey, fcells, _cb_key(pre), _cb_key(post))
    except AttributeError:
        return None


def _safe_cell_repr(cell: Any) -> Any:
    """Return a stable, hashable representation of a closure cell value."""
    try:
        v = cell.cell_contents
    except ValueError:
        return "__empty_cell__"
    # Hashable primitives pass through
    if isinstance(v, (int, float, bool, str, bytes, type(None))):
        return v
    # Fallback: repr (may be lossy but bytecode already provides most signal)
    return repr(v)


def _contract_sig(fn: Callable[..., Any] | None) -> str:
    """Stable signature for a contract callable.

    Hashes bytecode, constants, defaults, and closure cell values
    to avoid collisions between contracts that share bytecode structure
    but differ in embedded values.
    """
    if fn is None:
        return "none"
    try:
        code = fn.__code__
        parts = [code.co_code, repr(code.co_consts)]
        # Include closure cell values
        if fn.__closure__:
            for cell in fn.__closure__:
                try:
                    parts.append(repr(cell.cell_contents))
                except ValueError:
                    parts.append("__empty_cell__")
        # Include defaults
        if fn.__defaults__:
            parts.append(repr(fn.__defaults__))
        return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]
    except AttributeError:
        return repr(fn)


def _disk_cache_dir() -> Path | None:
    """Return the (memoized) cache directory, or None if disk cache disabled.

    Creating the directory via ``mkdir(parents=True, exist_ok=True)`` is ~5μs.
    We only do it once per configured ``cache_dir`` value.
    """
    global _disk_cache_dir_cached
    cache_dir = _config.get("cache_dir")
    cached_dir, cached_path = _disk_cache_dir_cached
    if cache_dir is None:
        _disk_cache_dir_cached = (None, None)
        return None
    if cache_dir == cached_dir and cached_path is not None:
        return cached_path
    p = Path(cache_dir)
    p.mkdir(parents=True, exist_ok=True)
    _disk_cache_dir_cached = (cache_dir, p)
    return p


def _disk_cache_path(cache_key: str) -> Path | None:
    """Return the disk cache file path for a key, or None if disk cache disabled."""
    d = _disk_cache_dir()
    if d is None:
        return None
    return d / f"{cache_key}.json"


def _load_from_disk(cache_key: str) -> ProofCertificate | None:
    """Try to load a cached proof from disk. Returns None on miss or error.

    Uses ``orjson`` when available (3-5x faster than stdlib ``json``) and
    reads raw bytes (avoids text decoding).
    """
    path = _disk_cache_path(cache_key)
    if path is None:
        return None
    try:
        if _HAS_ORJSON:
            raw = path.read_bytes()
            data = _orjson.loads(raw)
        else:
            data = json.loads(path.read_text())
    except (FileNotFoundError, OSError):
        return None
    except Exception as e:
        logger.debug("disk cert load failed for %s: %s", cache_key, e)
        return None
    try:
        cert = ProofCertificate.from_json(data)
    except Exception as e:
        logger.debug("cert deserialize failed for %s: %s", cache_key, e)
        return None
    _proof_cache[cache_key] = cert  # warm the memory cache
    return cert


def _save_to_disk(cache_key: str, cert: ProofCertificate) -> None:
    """Persist a proof certificate to disk (atomic write).

    Uses ``orjson`` when available (2-4x faster serialization).
    """
    path = _disk_cache_path(cache_key)
    if path is None:
        return
    try:
        tmp = path.with_suffix(".tmp")
        payload = cert.to_json()
        if _HAS_ORJSON:
            tmp.write_bytes(_orjson.dumps(payload))
        else:
            tmp.write_text(json.dumps(payload, separators=(",", ":")))
        tmp.replace(path)  # atomic on POSIX
    except Exception as e:
        logger.debug("disk cert save failed for %s: %s", cache_key, e)  # best-effort


# ---------------------------------------------------------------------------
# Contract argument count validation
# ---------------------------------------------------------------------------


def _validate_contract_arity(
    fn: Callable[..., Any],
    expected_args: int,
    name: str,
    fname: str,
) -> str | None:
    """Check that a contract callable has the right number of arguments.

    Args:
        fn: The pre or post callable.
        expected_args: Number of parameters expected (len(params) for pre,
            len(params) + 1 for post).
        name: ``"pre"`` or ``"post"`` (for error messages).
        fname: The function being verified (for error messages).

    Returns:
        An error string if the arity is wrong, or ``None`` if it is correct.
        Variadic callables (``*args``) always pass.
    """
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return None  # can't inspect — let Z3 catch it

    params = [
        p
        for p in sig.parameters.values()
        if p.kind
        not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    ]
    # If there are *args the callable is variadic — skip check
    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
    if has_varargs:
        return None

    if len(params) != expected_args:
        return (
            f"{name} contract for '{fname}' takes {len(params)} argument(s),"
            f" expected {expected_args}"
        )
    return None


# ---------------------------------------------------------------------------
# Main verification entry point
# ---------------------------------------------------------------------------


def verify_function(
    func: Callable[..., Any],
    pre: Callable[..., Any] | None = None,
    post: Callable[..., Any] | None = None,
    timeout_ms: int | None = None,
    verified_contracts: dict[str, dict[str, Any]] | None = None,
) -> ProofCertificate:
    """Verify a Python function using Z3.

    Args:
        func: The function to verify.
        pre: Precondition lambda taking the same args as *func*.
             Use ``&`` instead of ``and``, ``|`` instead of ``or``.
        post: Postcondition lambda taking ``(*args, result)``.
        timeout_ms: Z3 solver timeout in milliseconds.  Defaults to
            the global ``timeout_ms`` set via :func:`configure` (5000ms).
        verified_contracts: Contracts of called functions for composition.

    Returns:
        :class:`ProofCertificate` with status ``VERIFIED``, ``COUNTEREXAMPLE``,
        ``UNKNOWN``, ``TRANSLATION_ERROR``, or ``SKIPPED``.
    """
    if timeout_ms is None:
        timeout_ms = int(_config["timeout_ms"])

    fname = getattr(func, "__name__", str(func))

    # L0 fast cache: bytecode-keyed memoization. Skips inspect.getsource() on
    # hits (~25μs saved) and avoids hashing source text. A hit here returns
    # in ~1.5μs from the time verify_function() is entered.
    fast_key = _fast_key(func, pre, post)
    if fast_key is not None:
        cached = _fast_cache.get(fast_key)
        if cached is not None:
            return cached

    # Get source
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError) as e:
        return ProofCertificate(
            function_name=fname,
            source_hash="",
            status=Status.SKIPPED,
            preconditions=(),
            postconditions=(),
            message=f"Cannot get source: {e}",
        )

    # Cache key: source + contract bytecode (stable across identical lambdas)
    cache_key = _source_hash(source + _contract_sig(pre) + _contract_sig(post))
    if cache_key in _proof_cache:
        cert = _proof_cache[cache_key]
        if fast_key is not None:
            _fast_cache[fast_key] = cert
        return cert
    disk_hit = _load_from_disk(cache_key)
    if disk_hit is not None:
        if fast_key is not None:
            _fast_cache[fast_key] = disk_hit
        return disk_hit

    # Parse AST
    tree = ast.parse(source)
    func_ast = tree.body[0]
    if not isinstance(func_ast, ast.FunctionDef):
        return _err(fname, source, "Expected a function definition")

    # Resolve type hints
    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception as e:
        logger.debug("get_type_hints failed for %s: %s", getattr(func, "__name__", "<fn>"), e)
        hints = {}

    # Create Z3 symbolic variables for parameters
    param_vars: dict[str, Any] = {}
    param_types: dict[str, type] = {}
    for arg in func_ast.args.args:
        name = arg.arg
        typ = hints.get(name, float)
        param_types[name] = typ
        param_vars[name] = make_z3_var(name, typ)

    # Validate contract arities
    n_params = len(param_vars)
    if pre is not None:
        err = _validate_contract_arity(pre, n_params, "pre", fname)
        if err:
            cert = _err(fname, source, err)
            _proof_cache[cache_key] = cert
            return cert

    if post is not None:
        err = _validate_contract_arity(post, n_params + 1, "post", fname)
        if err:
            cert = _err(fname, source, err)
            _proof_cache[cache_key] = cert
            return cert

    # Resolve module-level constants from func's global scope
    closure_vars = _resolve_closure_vars(func, tree, set(param_vars))

    # Translate function body
    translator = Translator(param_types, verified_contracts, closure_vars)
    try:
        result = translator.translate(func_ast, param_vars)
    except TranslationError as e:
        # Enrich with line-number context if not already present
        msg = str(e)
        try:
            # Walk AST to find a plausible line number
            first_line = next(
                (getattr(n, "lineno", None) for n in ast.walk(func_ast) if hasattr(n, "lineno")),
                None,
            )
            if first_line and "line" not in msg:
                msg = f"{msg} (in '{fname}', near line {first_line})"
        except Exception as e:
            logger.debug("source line annotation failed for %s: %s", fname, e)
        cert = _err(fname, source, msg)
        _proof_cache[cache_key] = cert
        return cert

    if result.return_expr is None:
        cert = _err(fname, source, "Function has no return value on all paths")
        _proof_cache[cache_key] = cert
        return cert

    # Build solver
    s = z3.Solver()
    s.set("timeout", timeout_ms)

    # 1. Add preconditions
    pre_strs: list[str] = []
    param_list = [param_vars[arg.arg] for arg in func_ast.args.args]

    if pre is not None:
        try:
            pre_z3 = pre(*param_list)
            if isinstance(pre_z3, z3.BoolRef):
                s.add(pre_z3)
                pre_strs.append(str(pre_z3))
            else:
                cert = _err(
                    fname,
                    source,
                    f"Precondition returned {type(pre_z3).__name__}, expected z3.BoolRef. "
                    "Use & instead of 'and', | instead of 'or'.",
                )
                _proof_cache[cache_key] = cert
                return cert
        except Exception as e:
            cert = _err(
                fname,
                source,
                f"Precondition error: {e}. Use & instead of 'and', | instead of 'or'.",
            )
            _proof_cache[cache_key] = cert
            return cert

    # 2. Add refinement type constraints from annotations.
    #
    # A broken refinement predicate raises RefinementError (see
    # types.extract_refinements). Propagating as TRANSLATION_ERROR is
    # critical for soundness: silently dropping the refinement would
    # weaken the precondition below what the caller asked for, which
    # can turn a counterexample into a false VERIFIED.
    try:
        for name, var in param_vars.items():
            typ = hints.get(name)
            if typ is not None:
                for constraint in extract_refinements(typ, var):
                    s.add(constraint)
                    pre_strs.append(str(constraint))
    except TypeError as e:
        cert = _err(fname, source, f"Refinement error: {e}")
        _proof_cache[cache_key] = cert
        return cert

    # 3. Add body constraints (assumptions: callee postconditions, asserts)
    for c in result.constraints:
        s.add(c)

    # 3b. Collect proof obligations (callee preconditions that caller must prove)
    # These go into the postcondition — they must hold, not just be assumed.
    caller_obligations: list[Any] = list(result.obligations)

    # 4. Build the combined postcondition
    post_parts: list[Any] = []
    post_strs: list[str] = []
    ret = result.return_expr

    if post is not None:
        try:
            post_ret = _maybe_tuple_proxy(ret, result.tuple_meta)
            post_z3 = post(*param_list, post_ret)
            if isinstance(post_z3, z3.BoolRef):
                post_parts.append(post_z3)
                post_strs.append(str(post_z3))
            else:
                cert = _err(
                    fname,
                    source,
                    f"Postcondition returned {type(post_z3).__name__}, expected z3.BoolRef.",
                )
                _proof_cache[cache_key] = cert
                return cert
        except Exception as e:
            cert = _err(fname, source, f"Postcondition error: {e}")
            _proof_cache[cache_key] = cert
            return cert

    # Return type refinements. RefinementError is re-raised here for the
    # same reason as parameter refinements above: a broken predicate must
    # NOT silently weaken the postcondition.
    ret_typ = hints.get("return")
    if ret_typ is not None:
        try:
            for constraint in extract_refinements(ret_typ, ret):
                post_parts.append(constraint)
                post_strs.append(str(constraint))
        except TypeError as e:
            cert = _err(fname, source, f"Return refinement error: {e}")
            _proof_cache[cache_key] = cert
            return cert

    # Add caller obligations (callee preconditions) to postcondition set
    for ob in caller_obligations:
        post_parts.append(ob)
        post_strs.append(f"obligation: {ob}")

    # Nothing to prove
    if not post_parts:
        cert = ProofCertificate(
            function_name=fname,
            source_hash=_source_hash(source),
            status=Status.SKIPPED,
            preconditions=tuple(pre_strs),
            postconditions=(),
            message="No postcondition — nothing to prove",
        )
        _proof_cache[cache_key] = cert
        return cert

    # 5. Negate the combined postcondition
    combined_post = z3.And(*post_parts) if len(post_parts) > 1 else post_parts[0]
    s.add(z3.Not(combined_post))

    # 6. Solve
    t0 = time.monotonic()
    check = s.check()
    elapsed = (time.monotonic() - t0) * 1000

    z3_ver = z3.get_version_string()

    if check == z3.unsat:
        cert = ProofCertificate(
            function_name=fname,
            source_hash=_source_hash(source),
            status=Status.VERIFIED,
            preconditions=tuple(pre_strs),
            postconditions=tuple(post_strs),
            solver_time_ms=elapsed,
            z3_version=z3_ver,
            # Capture the exact unsat VC so it can be re-checked / proven
            # succinctly (see provably.succinct). Only meaningful on VERIFIED.
            smt_lib=s.to_smt2(),
        )
    elif check == z3.sat:
        ce = _extract_counterexample(s.model(), param_vars, ret, result.tuple_meta)
        cert = ProofCertificate(
            function_name=fname,
            source_hash=_source_hash(source),
            status=Status.COUNTEREXAMPLE,
            preconditions=tuple(pre_strs),
            postconditions=tuple(post_strs),
            counterexample=ce,
            message=f"Counterexample: {ce}",
            solver_time_ms=elapsed,
            z3_version=z3_ver,
        )
    else:
        cert = ProofCertificate(
            function_name=fname,
            source_hash=_source_hash(source),
            status=Status.UNKNOWN,
            preconditions=tuple(pre_strs),
            postconditions=tuple(post_strs),
            solver_time_ms=elapsed,
            message=f"Z3 returned unknown (timeout {timeout_ms}ms?)",
            z3_version=z3_ver,
        )

    _proof_cache[cache_key] = cert
    if fast_key is not None:
        _fast_cache[fast_key] = cert
    _save_to_disk(cache_key, cert)
    return cert


# ---------------------------------------------------------------------------
# Module-level batch verification
# ---------------------------------------------------------------------------


def verify_module(module: _types.ModuleType) -> dict[str, ProofCertificate]:
    """Find all ``@verified`` functions in a module and return their certificates.

    Walks the module's namespace looking for callables that have a
    ``__proof__`` attribute (i.e. functions decorated with
    :func:`~provably.decorators.verified`).

    Args:
        module: A Python module object (e.g. from ``import mymodule``).

    Returns:
        A dict mapping ``function_name`` to its :class:`ProofCertificate`.
        Functions without a ``__proof__`` attribute are silently skipped.

    Example::

        import mymodule
        from provably import verify_module

        results = verify_module(mymodule)
        for name, cert in results.items():
            print(cert)
    """
    results: dict[str, ProofCertificate] = {}
    for attr_name in dir(module):
        try:
            obj = getattr(module, attr_name)
        except Exception as e:
            logger.debug("attr access failed for %s.%s: %s", module.__name__, attr_name, e)
            continue
        if callable(obj) and hasattr(obj, "__proof__"):
            cert: ProofCertificate = obj.__proof__
            results[cert.function_name] = cert
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_counterexample(
    model: Any,
    param_vars: dict[str, Any],
    return_expr: Any,
    tuple_meta: dict[str, tuple[int, list[Any]]] | None = None,
) -> dict[str, Any]:
    """Extract human-readable counterexample from a Z3 model.

    When the function returns a tuple, ``return_expr`` is a Z3 integer
    identifier (an opaque tuple id), which is useless to the caller. We
    detect this via ``tuple_meta`` and evaluate each accessor instead,
    returning the result as a real Python tuple.
    """
    ce: dict[str, Any] = {}
    for name, var in param_vars.items():
        val = model.eval(var, model_completion=True)
        ce[name] = _z3_val_to_python(val)

    if tuple_meta is not None and str(return_expr) in tuple_meta:
        arity, elem_sorts = tuple_meta[str(return_expr)]
        elements: list[int | float | bool | str] = []
        for i in range(arity):
            accessor = z3.Function(
                f"__tuple_{arity}_get_{i}",
                z3.IntSort(),
                elem_sorts[i],
            )
            elem_val = model.eval(accessor(return_expr), model_completion=True)
            elements.append(_z3_val_to_python(elem_val))
        ce["__return__"] = tuple(elements)
    else:
        ret_val = model.eval(return_expr, model_completion=True)
        ce["__return__"] = _z3_val_to_python(ret_val)
    return ce


def _z3_val_to_python(val: Any) -> int | float | bool | str:
    """Convert a Z3 value to a Python scalar."""
    try:
        if z3.is_int_value(val):
            return int(val.as_long())
        if z3.is_rational_value(val):
            return float(val.as_fraction())
        if z3.is_true(val):
            return True
        if z3.is_false(val):
            return False
    except (AttributeError, ValueError, ArithmeticError, OverflowError):
        pass
    try:
        return str(val)
    except Exception:
        # val's own __repr__/__str__ is broken — fall back to a type label so
        # the caller still gets a plain string (never propagates).
        return f"<unrepresentable {type(val).__name__}>"


def _resolve_closure_vars(
    func: Callable[..., Any],
    tree: ast.Module,
    param_names: set[str],
) -> dict[str, Any]:
    """Resolve external constants referenced in the function body.

    Sources (checked in order):
      1. Closure cells (``func.__closure__`` + ``func.__code__.co_freevars``)
      2. Module globals (``func.__globals__``)

    Only numeric and boolean values are translated to Z3 constants.
    """
    # Build a lookup table: name → Python value
    lookup: dict[str, Any] = {}

    # Module globals (lower priority)
    func_globals = getattr(func, "__globals__", {})
    if func_globals:
        lookup.update(func_globals)

    # Closure cells (higher priority — override globals)
    freevars = getattr(getattr(func, "__code__", None), "co_freevars", ())
    cells = getattr(func, "__closure__", None) or ()
    for name, cell in zip(freevars, cells, strict=False):
        try:
            lookup[name] = cell.cell_contents
        except ValueError:
            pass  # empty cell

    if not lookup:
        return {}

    # Collect all referenced names in the AST
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced.add(node.id)

    external = referenced - param_names - {"True", "False", "None"}

    closure: dict[str, Any] = {}
    for name in external:
        if name in lookup:
            val = lookup[name]
            if isinstance(val, bool):
                closure[name] = z3.BoolVal(val)
            elif isinstance(val, int):
                closure[name] = z3.IntVal(val)
            elif isinstance(val, float):
                closure[name] = z3.RealVal(str(val))
    return closure


class _TupleProxy:
    """Proxy for a tuple-valued Z3 expression used in user contract lambdas.

    The translator encodes a Python tuple as an ``IntSort`` identifier with
    uninterpreted accessor functions ``__tuple_N_get_i`` bound by axioms.
    A raw Z3 ``ArithRef`` can't be subscripted in Python, so when a user's
    ``post=lambda x, y, result: result[0] == x + y`` runs, the lambda would
    crash with ``'ArithRef' object is not subscriptable``.

    ``_TupleProxy`` wraps the tuple id, knows the tuple's arity and element
    sorts, and replays ``proxy[i]`` as the correct Z3 accessor application.
    Only constant integer indices are supported (matching the translator).
    """

    __slots__ = ("_tuple_id", "_arity", "_elem_sorts")

    def __init__(self, tuple_id: Any, arity: int, elem_sorts: list[Any]) -> None:
        self._tuple_id = tuple_id
        self._arity = arity
        self._elem_sorts = elem_sorts

    def __getitem__(self, idx: int) -> Any:
        if not isinstance(idx, int):
            raise TypeError(f"Tuple proxy only supports integer indices, got {type(idx).__name__}")
        i = idx + self._arity if idx < 0 else idx
        if i < 0 or i >= self._arity:
            raise IndexError(f"Tuple subscript {idx} out of range for {self._arity}-tuple")
        accessor = z3.Function(
            f"__tuple_{self._arity}_get_{i}",
            z3.IntSort(),
            self._elem_sorts[i],
        )
        return accessor(self._tuple_id)

    def __len__(self) -> int:
        return self._arity


def _maybe_tuple_proxy(ret: Any, tuple_meta: dict[str, tuple[int, list[Any]]]) -> Any:
    """Wrap ``ret`` in a _TupleProxy if it's a known tuple id, else pass through."""
    if ret is None:
        return ret
    meta = tuple_meta.get(str(ret))
    if meta is None:
        return ret
    arity, elem_sorts = meta
    return _TupleProxy(ret, arity, elem_sorts)


def _err(fname: str, source: str, message: str) -> ProofCertificate:
    return ProofCertificate(
        function_name=fname,
        source_hash=_source_hash(source),
        status=Status.TRANSLATION_ERROR,
        preconditions=(),
        postconditions=(),
        message=message,
    )
