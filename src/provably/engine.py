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

from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, get_type_hints
import types as _types

from .translator import Translator, TranslationError, HAS_Z3
from .types import make_z3_var, extract_refinements

if HAS_Z3:
    import z3


# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------

_config: dict[str, Any] = {
    "timeout_ms": 5000,
    "raise_on_failure": False,
    "log_level": "WARNING",
}


def configure(**kwargs: Any) -> None:
    """Set global verification defaults.

    Supported keys:

    - ``timeout_ms`` (int): Z3 solver timeout in milliseconds (default 5000).
    - ``raise_on_failure`` (bool): Raise :class:`~provably.decorators.VerificationError`
      when a proof fails (default ``False``).
    - ``log_level`` (str): Python logging level for the ``provably`` logger
      (default ``"WARNING"``).

    Example::

        from provably import configure
        configure(timeout_ms=10_000, raise_on_failure=True)

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
        logging.getLogger("provably").setLevel(getattr(logging, kwargs["log_level"], logging.WARNING))


# ---------------------------------------------------------------------------
# Status + ProofCertificate
# ---------------------------------------------------------------------------

class Status(Enum):
    """Verification result status."""

    VERIFIED = "verified"
    COUNTEREXAMPLE = "counterexample"
    UNKNOWN = "unknown"
    TRANSLATION_ERROR = "translation_error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
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

    function_name: str
    source_hash: str
    status: Status
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    counterexample: dict[str, Any] | None = None
    message: str = ""
    solver_time_ms: float = 0.0
    z3_version: str = ""

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
                if isinstance(v, (int, float, bool, str, type(None))):
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
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ProofCertificate":
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
        )


# ---------------------------------------------------------------------------
# Proof cache (content-addressed by source + contract hash)
# ---------------------------------------------------------------------------

_proof_cache: dict[str, ProofCertificate] = {}


def clear_cache() -> None:
    """Clear the global proof cache."""
    _proof_cache.clear()


def _source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _contract_sig(fn: Callable[..., Any] | None) -> str:
    """Stable signature for a contract callable (bytecode-based)."""
    if fn is None:
        return "none"
    try:
        return hashlib.sha256(fn.__code__.co_code).hexdigest()[:12]
    except AttributeError:
        return repr(fn)


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
        p for p in sig.parameters.values()
        if p.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    ]
    # If there are *args the callable is variadic — skip check
    has_varargs = any(
        p.kind == inspect.Parameter.VAR_POSITIONAL
        for p in sig.parameters.values()
    )
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

    if not HAS_Z3:
        return ProofCertificate(
            function_name=fname,
            source_hash="",
            status=Status.SKIPPED,
            preconditions=(),
            postconditions=(),
            message=(
                "z3-solver not installed. "
                "Run: pip install 'provably[z3]'"
            ),
        )

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
        return _proof_cache[cache_key]

    # Parse AST
    tree = ast.parse(source)
    func_ast = tree.body[0]
    if not isinstance(func_ast, ast.FunctionDef):
        return _err(fname, source, "Expected a function definition")

    # Resolve type hints
    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
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
        except Exception:
            pass
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
        except Exception as e:
            cert = _err(
                fname,
                source,
                f"Precondition error: {e}. Use & instead of 'and', | instead of 'or'.",
            )
            _proof_cache[cache_key] = cert
            return cert

    # 2. Add refinement type constraints from annotations
    for name, var in param_vars.items():
        typ = hints.get(name)
        if typ is not None:
            for constraint in extract_refinements(typ, var):
                s.add(constraint)
                pre_strs.append(str(constraint))

    # 3. Add body constraints (from assert statements + verified calls)
    for c in result.constraints:
        s.add(c)

    # 4. Build the combined postcondition
    post_parts: list[Any] = []
    post_strs: list[str] = []
    ret = result.return_expr

    if post is not None:
        try:
            post_z3 = post(*param_list, ret)
            if isinstance(post_z3, z3.BoolRef):
                post_parts.append(post_z3)
                post_strs.append(str(post_z3))
        except Exception as e:
            cert = _err(fname, source, f"Postcondition error: {e}")
            _proof_cache[cache_key] = cert
            return cert

    # Return type refinements
    ret_typ = hints.get("return")
    if ret_typ is not None:
        for constraint in extract_refinements(ret_typ, ret):
            post_parts.append(constraint)
            post_strs.append(str(constraint))

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
        )
    elif check == z3.sat:
        ce = _extract_counterexample(s.model(), param_vars, ret)
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
    return cert


# ---------------------------------------------------------------------------
# Module-level batch verification
# ---------------------------------------------------------------------------

def verify_module(module: "_types.ModuleType") -> dict[str, ProofCertificate]:
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
        except Exception:
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
) -> dict[str, Any]:
    """Extract human-readable counterexample from a Z3 model."""
    ce: dict[str, Any] = {}
    for name, var in param_vars.items():
        val = model.eval(var, model_completion=True)
        ce[name] = _z3_val_to_python(val)
    ret_val = model.eval(return_expr, model_completion=True)
    ce["__return__"] = _z3_val_to_python(ret_val)
    return ce


def _z3_val_to_python(val: Any) -> int | float | bool | str:
    """Convert a Z3 value to a Python scalar."""
    try:
        if z3.is_int_value(val):
            return val.as_long()
        if z3.is_rational_value(val):
            return float(val.as_fraction())
        if z3.is_true(val):
            return True
        if z3.is_false(val):
            return False
    except (AttributeError, ValueError, ArithmeticError, OverflowError):
        pass
    return str(val)


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
    for name, cell in zip(freevars, cells):
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


def _err(fname: str, source: str, message: str) -> ProofCertificate:
    return ProofCertificate(
        function_name=fname,
        source_hash=_source_hash(source),
        status=Status.TRANSLATION_ERROR,
        preconditions=(),
        postconditions=(),
        message=message,
    )
