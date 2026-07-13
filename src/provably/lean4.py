"""Lean4 backend — generate and check Lean4 proofs from @verified contracts.

Translates Python functions with pre/post conditions into Lean4 theorem
statements + tactic proofs. The Lean4 type checker then serves as an
independent verification oracle (cross-checking Z3 results).

Pipeline:
    1. Parse function AST + contracts (same as Z3 backend)
    2. Generate Lean4 theorem statement from pre/post
    3. Generate tactic proof sketch (nlinarith/omega/simp/linarith)
    4. Write to temp .lean file
    5. Run `lean` to type-check
    6. Return ProofCertificate with status and lean4 proof text

Requirements:
    - Lean4 installed (via elan): `brew install elan-init && elan default stable`
    - No Mathlib needed for basic arithmetic theorems (uses Lean4 stdlib)

Limitations:
    - Supports a strict arithmetic/control-flow subset, smaller than the Z3 backend
    - Unsupported or non-total control flow is rejected rather than admitted
    - Transcendental functions, loops, recursion, and data structures are not supported
    - Slower than Z3 (compiles to native code)
"""

from __future__ import annotations  # pragma: no cover

import ast  # pragma: no cover
import hashlib  # pragma: no cover
import inspect  # pragma: no cover
import re  # pragma: no cover
import subprocess  # pragma: no cover
import tempfile  # pragma: no cover
import textwrap  # pragma: no cover
import time  # pragma: no cover
from pathlib import Path  # pragma: no cover
from typing import Any  # pragma: no cover

from .engine import ProofCertificate, Status  # pragma: no cover

# Check if lean is available
try:  # pragma: no cover
    _lean_result = subprocess.run(
        ["lean", "--version"], capture_output=True, text=True, timeout=10
    )
    HAS_LEAN4 = _lean_result.returncode == 0
    LEAN4_VERSION = _lean_result.stdout.strip().split("\n")[0] if HAS_LEAN4 else ""
except (FileNotFoundError, subprocess.TimeoutExpired):
    HAS_LEAN4 = False
    LEAN4_VERSION = ""


# =============================================================================
# AST → LEAN4 TRANSLATION
# =============================================================================


def _py_type_to_lean(typ: type | None) -> str:
    """Map Python type annotation to Lean4 type."""
    if typ is None or typ is float:
        return "Float"
    if typ is int:
        return "Int"
    if typ is bool:
        return "Bool"
    # Handle Annotated types — strip metadata, use base
    origin = getattr(typ, "__origin__", None)
    if origin is not None:
        args = getattr(typ, "__args__", ())
        if args:
            return _py_type_to_lean(args[0])
    return "Float"


def _expr_to_lean(node: ast.expr, env: dict[str, str] | None = None) -> str:
    """Translate a Python AST expression to Lean4 syntax."""
    if env is None:
        env = {}

    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            # Decimal notation is polymorphic in Lean.  The surrounding
            # implementation type determines ℝ; forcing ``Float`` here made
            # the mathlib-mode definition ill-typed.
            return str(v)
        raise ValueError(f"Unsupported Lean4 constant: {v!r}")

    if isinstance(node, ast.Name):
        return env.get(node.id, node.id)

    if isinstance(node, ast.BinOp):
        left = _expr_to_lean(node.left, env)
        right = _expr_to_lean(node.right, env)
        op_map = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
        }
        op = op_map.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported Lean4 binary operator: {type(node.op).__name__}")
        return f"({left} {op} {right})"

    if isinstance(node, ast.UnaryOp):
        operand = _expr_to_lean(node.operand, env)
        if isinstance(node.op, ast.USub):
            return f"(-{operand})"
        if isinstance(node.op, ast.Not):
            return f"(¬ {operand})"
        raise ValueError(f"Unsupported Lean4 unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.Compare):
        parts = []
        left = _expr_to_lean(node.left, env)
        cmp_map: dict[type, str] = {
            ast.Lt: "<",
            ast.LtE: "≤",
            ast.Gt: ">",
            ast.GtE: "≥",
            ast.Eq: "=",
            ast.NotEq: "≠",
        }
        for cmp_op, comparator in zip(node.ops, node.comparators, strict=False):
            right = _expr_to_lean(comparator, env)
            sym = cmp_map.get(type(cmp_op))
            if sym is None:
                raise ValueError(f"Unsupported Lean4 comparison operator: {type(cmp_op).__name__}")
            parts.append(f"{left} {sym} {right}")
            left = right
        if len(parts) == 1:
            return parts[0]
        return " ∧ ".join(f"({p})" for p in parts)

    if isinstance(node, ast.BoolOp):
        values = [_expr_to_lean(v, env) for v in node.values]
        if isinstance(node.op, ast.And):
            return " ∧ ".join(f"({v})" for v in values)
        return " ∨ ".join(f"({v})" for v in values)

    if isinstance(node, ast.IfExp):
        test = _expr_to_lean(node.test, env)
        body = _expr_to_lean(node.body, env)
        orelse = _expr_to_lean(node.orelse, env)
        return f"(if {test} then {body} else {orelse})"

    if isinstance(node, ast.Call):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        args = [_expr_to_lean(a, env) for a in node.args]
        builtin_map = {
            "min": lambda a: f"(min {a[0]} {a[1]})" if len(a) == 2 else f"min {' '.join(a)}",
            "max": lambda a: f"(max {a[0]} {a[1]})" if len(a) == 2 else f"max {' '.join(a)}",
            "abs": lambda a: f"(|{a[0]}|)" if len(a) == 1 else f"abs {' '.join(a)}",
        }
        expected_arity = {"min": 2, "max": 2, "abs": 1}
        if func_name not in builtin_map:
            raise ValueError(f"Unsupported Lean4 call: {func_name or ast.dump(node.func)}")
        if len(args) != expected_arity[func_name]:
            raise ValueError(
                f"Lean4 call {func_name} expects {expected_arity[func_name]} argument(s)"
            )
        return builtin_map[func_name](args)

    raise ValueError(f"Unsupported Lean4 expression: {type(node).__name__}")


def _if_to_lean(stmt: ast.If, env: dict[str, str]) -> str:
    """Translate a standalone if/elif/else expression.

    A branch without a return is rejected.  Generating a Lean ``sorry`` here
    used to let the compiler exit successfully and could therefore create a
    false ``VERIFIED`` certificate.
    """
    return _statements_to_lean([stmt], env)


def _statements_to_lean(statements: list[ast.stmt], env: dict[str, str]) -> str:
    """Translate a terminating statement sequence to one Lean term.

    The continuation is threaded into both sides of an ``if``.  This preserves
    Python fall-through such as ``if ...: return a; return b`` without an
    incomplete branch placeholder.
    """
    if not statements:
        raise ValueError("Lean4 translation requires every control-flow path to return")

    stmt, *rest = statements
    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            raise ValueError("Lean4 backend does not support bare return")
        return _expr_to_lean(stmt.value, env)

    if isinstance(stmt, ast.If):
        test = _expr_to_lean(stmt.test, env)
        then_term = _statements_to_lean([*stmt.body, *rest], env.copy())
        else_term = _statements_to_lean([*stmt.orelse, *rest], env.copy())
        return f"if {test} then {then_term} else {else_term}"

    if isinstance(stmt, ast.Assign):
        next_env = env.copy()
        bindings: list[tuple[str, str]] = []
        for target in stmt.targets:
            if not isinstance(target, ast.Name):
                raise ValueError("Lean4 backend only supports assignment to local names")
            value = _expr_to_lean(stmt.value, next_env)
            next_env[target.id] = target.id
            bindings.append((target.id, value))
        tail = _statements_to_lean(rest, next_env)
        for name, value in reversed(bindings):
            tail = f"let {name} := {value}\n  {tail}"
        return tail

    if isinstance(stmt, ast.AnnAssign):
        if stmt.value is None or not isinstance(stmt.target, ast.Name):
            raise ValueError("Lean4 backend requires a named initialized annotation")
        value = _expr_to_lean(stmt.value, env)
        next_env = env.copy()
        next_env[stmt.target.id] = stmt.target.id
        return f"let {stmt.target.id} := {value}\n  {_statements_to_lean(rest, next_env)}"

    if isinstance(stmt, ast.AugAssign):
        if not isinstance(stmt.target, ast.Name):
            raise ValueError("Lean4 backend only supports augmented assignment to local names")
        op_map = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
        op = op_map.get(type(stmt.op))
        if op is None:
            raise ValueError(f"Unsupported augmented assignment: {type(stmt.op).__name__}")
        name = stmt.target.id
        current = env.get(name, name)
        value = _expr_to_lean(stmt.value, env)
        next_env = env.copy()
        next_env[name] = name
        return f"let {name} := ({current} {op} {value})\n  {_statements_to_lean(rest, next_env)}"

    if isinstance(stmt, ast.Pass) or (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    ):
        return _statements_to_lean(rest, env)

    raise ValueError(f"Unsupported Lean4 statement: {type(stmt).__name__}")


def _func_body_to_lean(func_ast: ast.FunctionDef, env: dict[str, str]) -> str:
    """Translate function body to a Lean4 definition body."""
    return _statements_to_lean(func_ast.body, env.copy())


# =============================================================================
# LEAN4 THEOREM GENERATION
# =============================================================================


def generate_lean4_theorem(
    func_name: str,
    param_names: list[str],
    param_types: dict[str, type],
    pre_str: str | None,
    post_str: str | None,
    source: str,
) -> str:
    """Generate a complete Lean4 file with theorem statement + proof attempt.

    Chooses between TWO output modes:

    * **core** (kernel-clean, no Mathlib): emitted whenever every parameter
      and the return are ``Int`` or ``Bool``. Returns an ``Int``/``Bool``
      def and uses only core tactics (``omega``, ``decide``, ``split``,
      ``rfl``). The output is independent of Mathlib and passes
      ``#print axioms`` with only the standard foundational axioms.

    * **mathlib** (requires Mathlib on the Lean search path): emitted when
      any parameter or the return is ``float`` and we therefore need ℝ.
      Uses ``nlinarith``/``linarith`` from Mathlib. If Mathlib isn't
      available at check time, ``check_lean4_proof`` will report the
      missing-import failure honestly rather than silently "passing".
    """
    tree = ast.parse(source)
    func_ast = tree.body[0]
    if not isinstance(func_ast, ast.FunctionDef):
        raise ValueError("Lean4 translation source is not a function definition")

    # Pick the output mode from parameter types.
    all_int_or_bool = all(param_types.get(name, float) in (int, bool) for name in param_names)
    # Crude return-type check — the decorator already filters out
    # unsupported annotations so ``float`` is the only 'must use ℝ'.
    ret_hint: type | None = None
    returns = getattr(func_ast, "returns", None)
    if isinstance(returns, ast.Name):
        if returns.id == "int":
            ret_hint = int
        elif returns.id == "bool":
            ret_hint = bool
        elif returns.id == "float":
            ret_hint = float
    core_mode = all_int_or_bool and ret_hint in (int, bool, None)

    params = []
    for name in param_names:
        typ = param_types.get(name, float)
        lean_type = _py_type_to_lean(typ)
        if not core_mode and lean_type == "Float":
            lean_type = "ℝ"
        params.append(f"({name} : {lean_type})")
    param_decl = " ".join(params)

    env = {n: n for n in param_names}
    body = _func_body_to_lean(func_ast, env)

    return_type = (
        "Int"
        if core_mode and ret_hint is int
        else "Bool"
        if core_mode and ret_hint is bool
        else "Int"
        if core_mode
        else "ℝ"
    )
    def_kw = "def" if core_mode else "noncomputable def"

    lean_lines = [
        "-- Auto-generated by provably.lean4",
        f"-- Source: @verified function '{func_name}'",
        f"-- Mode: {'core (kernel-clean, no Mathlib)' if core_mode else 'mathlib (requires Mathlib)'}",
        "",
    ]
    if not core_mode:
        lean_lines.append("import Mathlib.Tactic")
        lean_lines.append("")
    lean_lines.extend(
        [
            f"{def_kw} {func_name}_impl {param_decl} : {return_type} :=",
            f"  {body}",
            "",
        ]
    )

    # Pick a tactic that stays in the chosen mode.
    if core_mode:
        tactic = "split <;> first | omega | decide | rfl | (intro h_pre; omega)"
    else:
        tactic = "split_ifs <;> nlinarith"

    if pre_str and post_str:
        lean_lines.extend(
            [
                f"theorem {func_name}_verified {param_decl}",
                f"  (h_pre : {pre_str})",
                f"  : {post_str} := by",
                f"  unfold {func_name}_impl",
                f"  {tactic}",
            ]
        )
    elif post_str:
        lean_lines.extend(
            [
                f"theorem {func_name}_verified {param_decl}",
                f"  : {post_str} := by",
                f"  unfold {func_name}_impl",
                f"  {tactic}",
            ]
        )
    else:
        lean_lines.append(f"-- No postcondition to prove for {func_name}")

    if core_mode:
        # Helps the reader audit kernel-cleanness.
        lean_lines.extend(
            [
                "",
                f"-- To audit: #print axioms {func_name}_verified",
                "-- A kernel-clean proof depends only on propext, Quot.sound,",
                "-- Classical.choice (and their ilk) — never 'sorry' or Mathlib.",
            ]
        )

    return "\n".join(lean_lines)


def _z3_str_to_lean(z3_str: str, param_names: list[str]) -> str:
    """Convert Z3 string representation to Lean4 syntax.

    Z3 outputs like: And(x >= 0, x <= 1)
    Lean4 wants: (x ≥ 0) ∧ (x ≤ 1)
    """

    def split_args(text: str) -> list[str]:
        args: list[str] = []
        depth = 0
        start = 0
        for index, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                args.append(text[start:index].strip())
                start = index + 1
        args.append(text[start:].strip())
        return args

    def convert(text: str) -> str:
        text = text.strip()
        for head, connective in (("And", "∧"), ("Or", "∨")):
            prefix = f"{head}("
            if text.startswith(prefix) and text.endswith(")"):
                parts = split_args(text[len(prefix) : -1])
                return f" {connective} ".join(f"({convert(part)})" for part in parts)
        if text.startswith("Not(") and text.endswith(")"):
            return f"¬({convert(text[4:-1])})"
        return text.replace(">=", "≥").replace("<=", "≤").replace("!=", "≠")

    return convert(z3_str)


# =============================================================================
# LEAN4 PROOF CHECKING
# =============================================================================


_ALLOWED_LEAN_AXIOMS = {
    "propext",
    "Classical.choice",
    "Quot.sound",
    "Lean.ofReduceBool",
    "Lean.reduceBool",
    "Lean.trustCompiler",
}


def _contains_placeholder(lean_code: str) -> bool:
    """Return whether executable Lean contains an admitted proof surface."""
    without_blocks = re.sub(r"/-(?:.|\n)*?-/", "", lean_code)
    without_comments = re.sub(r"--[^\n]*", "", without_blocks)
    return bool(
        re.search(r"\bsorry\b", without_comments)
        or re.search(r"^\s*axiom\s+", without_comments, re.MULTILINE)
    )


def check_lean4_proof(
    lean_code: str,
    timeout_s: float = 60.0,
    theorem_name: str | None = None,
) -> tuple[bool, str]:
    """Write Lean4 code to a temp file and check it.

    Returns (success, output).
    """
    if _contains_placeholder(lean_code):
        return False, "Lean4 proof contains an admitted `sorry` or `axiom` placeholder"

    if not HAS_LEAN4:
        return False, "Lean4 not installed"

    checked_code = lean_code
    if theorem_name is not None:
        checked_code += f"\n\n#print axioms {theorem_name}\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".lean", delete=False, prefix="provably_"
    ) as f:
        f.write(checked_code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["lean", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return False, output
        if "declaration uses 'sorry'" in output or "sorryAx" in output:
            return False, f"Lean4 reported an admitted declaration: {output}"
        if theorem_name is not None:
            escaped = re.escape(theorem_name)
            depends = re.search(rf"'{escaped}' depends on axioms: \[([^]]*)\]", output)
            no_axioms = re.search(rf"'{escaped}' does not depend on any axioms", output)
            if depends is None and no_axioms is None:
                return False, f"Lean4 axiom audit produced no result for {theorem_name}: {output}"
            axioms = (
                {item.strip() for item in depends.group(1).split(",") if item.strip()}
                if depends is not None
                else set()
            )
            unexpected = axioms - _ALLOWED_LEAN_AXIOMS
            if unexpected:
                return False, f"Lean4 theorem depends on disallowed axioms: {sorted(unexpected)}"
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"Lean4 timed out after {timeout_s}s"
    except FileNotFoundError:
        return False, "lean command not found"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# =============================================================================
# STANDALONE LEAN4 VERIFICATION (no Z3)
# =============================================================================


def verify_with_lean4(
    func: Any,
    pre: Any | None = None,
    post: Any | None = None,
    timeout_s: float = 60.0,
) -> ProofCertificate:
    """Verify a function using Lean4 instead of (or in addition to) Z3.

    Same interface as verify_function but uses Lean4 type checker.
    """
    import z3 as _z3

    from .types import extract_refinements, make_z3_var

    fname = getattr(func, "__name__", str(func))

    if not HAS_LEAN4:
        return ProofCertificate(
            function_name=fname,
            source_hash="",
            status=Status.SKIPPED,
            preconditions=(),
            postconditions=(),
            message="Lean4 not installed (install via: brew install elan-init && elan default stable)",
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

    # Parse
    tree = ast.parse(source)
    func_ast_raw = tree.body[0]
    if not isinstance(func_ast_raw, ast.FunctionDef):
        return ProofCertificate(
            function_name=fname,
            source_hash="",
            status=Status.TRANSLATION_ERROR,
            preconditions=(),
            postconditions=(),
            message="Not a function definition",
        )
    func_ast: ast.FunctionDef = func_ast_raw

    # Extract param info
    try:
        from typing import get_type_hints

        hints = get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}

    param_names = [arg.arg for arg in func_ast.args.args]
    param_types: dict[str, type] = {}
    param_vars: dict[str, Any] = {}
    for name in param_names:
        typ = hints.get(name, float)
        param_types[name] = typ
        param_vars[name] = make_z3_var(name, typ)

    # Build Z3 string representations of pre/post.
    #
    # Soundness rule: if the user's pre/post lambdas raise when evaluated
    # against symbolic Z3 variables we must NOT silently discard the
    # constraint — doing so would let Lean4 "prove" too much (pre = True).
    # Return a translation-error certificate instead so the caller can see
    # WHY verification refused.
    pre_strs: list[str] = []
    post_strs: list[str] = []
    param_list = [param_vars[n] for n in param_names]

    if pre is not None:
        try:
            pre_z3 = pre(*param_list)
        except Exception as e:  # noqa: BLE001 — surfaced as cert
            return ProofCertificate(
                function_name=fname,
                source_hash="",
                status=Status.TRANSLATION_ERROR,
                preconditions=(),
                postconditions=(),
                message=f"Precondition error: {e}",
            )
        if not isinstance(pre_z3, _z3.BoolRef):
            return ProofCertificate(
                function_name=fname,
                source_hash="",
                status=Status.TRANSLATION_ERROR,
                preconditions=(),
                postconditions=(),
                message="Precondition must produce a symbolic Boolean expression",
            )
        pre_strs.append(str(pre_z3))

    # Add refinement constraints
    try:
        for name, var in param_vars.items():
            typ = hints.get(name)
            if typ is not None:
                for constraint in extract_refinements(typ, var):
                    pre_strs.append(str(constraint))
    except TypeError as e:
        return ProofCertificate(
            function_name=fname,
            source_hash="",
            status=Status.TRANSLATION_ERROR,
            preconditions=(),
            postconditions=(),
            message=f"Refinement error: {e}",
        )

    if post is None:
        return ProofCertificate(
            function_name=fname,
            source_hash=hashlib.sha256(source.encode()).hexdigest()[:16],
            status=Status.SKIPPED,
            preconditions=tuple(pre_strs),
            postconditions=(),
            message="Lean4 verification requires an explicit postcondition",
        )

    if post is not None:
        # Match the symbolic result sort to the Python return annotation.
        # Using Real unconditionally made Int/Bool contracts describe a
        # different theorem from the generated implementation.
        result_type = hints.get("return", float)
        try:
            result_var = make_z3_var("result", result_type)
        except TypeError as e:
            return ProofCertificate(
                function_name=fname,
                source_hash="",
                status=Status.TRANSLATION_ERROR,
                preconditions=tuple(pre_strs),
                postconditions=(),
                message=f"Return type error: {e}",
            )
        try:
            post_z3 = post(*param_list, result_var)
        except Exception as e:  # noqa: BLE001 — surfaced as cert
            return ProofCertificate(
                function_name=fname,
                source_hash="",
                status=Status.TRANSLATION_ERROR,
                preconditions=(),
                postconditions=(),
                message=f"Postcondition error: {e}",
            )
        if not isinstance(post_z3, _z3.BoolRef):
            return ProofCertificate(
                function_name=fname,
                source_hash="",
                status=Status.TRANSLATION_ERROR,
                preconditions=tuple(pre_strs),
                postconditions=(),
                message="Postcondition must produce a symbolic Boolean expression",
            )
        post_strs.append(str(post_z3))

    # Convert to Lean4 syntax
    pre_lean = (
        " ∧ ".join(f"({_z3_str_to_lean(s, param_names)})" for s in pre_strs) if pre_strs else None
    )
    post_lean = (
        " ∧ ".join(f"({_z3_str_to_lean(s, param_names)})" for s in post_strs)
        if post_strs
        else None
    )

    # Replace 'result' with the actual function definition body
    if post_lean:
        post_lean = post_lean.replace("result", f"({fname}_impl {' '.join(param_names)})")

    # Generate Lean4 code
    try:
        lean_code = generate_lean4_theorem(
            func_name=fname,
            param_names=param_names,
            param_types=param_types,
            pre_str=pre_lean,
            post_str=post_lean,
            source=source,
        )
    except ValueError as e:
        return ProofCertificate(
            function_name=fname,
            source_hash=hashlib.sha256(source.encode()).hexdigest()[:16],
            status=Status.TRANSLATION_ERROR,
            preconditions=tuple(pre_strs),
            postconditions=tuple(post_strs),
            message=f"Lean4 translation error: {e}",
        )

    if _contains_placeholder(lean_code):
        return ProofCertificate(
            function_name=fname,
            source_hash=hashlib.sha256(source.encode()).hexdigest()[:16],
            status=Status.TRANSLATION_ERROR,
            preconditions=tuple(pre_strs),
            postconditions=tuple(post_strs),
            message="Lean4 translation produced an admitted placeholder",
        )

    # Check with Lean4
    t0 = time.monotonic()
    success, output = check_lean4_proof(
        lean_code,
        timeout_s=timeout_s,
        theorem_name=f"{fname}_verified",
    )
    elapsed = (time.monotonic() - t0) * 1000

    source_hash = hashlib.sha256(source.encode()).hexdigest()[:16]

    if success:
        return ProofCertificate(
            function_name=fname,
            source_hash=source_hash,
            status=Status.VERIFIED,
            preconditions=tuple(pre_strs),
            postconditions=tuple(post_strs),
            solver_time_ms=elapsed,
            z3_version=f"lean4:{LEAN4_VERSION}",
            message="Lean4 type-checked successfully",
        )
    else:
        return ProofCertificate(
            function_name=fname,
            source_hash=source_hash,
            status=Status.UNKNOWN,
            preconditions=tuple(pre_strs),
            postconditions=tuple(post_strs),
            solver_time_ms=elapsed,
            z3_version=f"lean4:{LEAN4_VERSION}",
            message=f"Lean4 proof failed: {output[:500]}",
        )


def export_lean4(
    func: Any,
    pre: Any | None = None,
    post: Any | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Export a @verified function as a Lean4 theorem file.

    Returns the Lean4 source code. Optionally writes to output_path.
    """
    import z3 as _z3

    from .types import extract_refinements, make_z3_var

    fname = getattr(func, "__name__", str(func))
    source = textwrap.dedent(inspect.getsource(func))

    tree = ast.parse(source)
    func_ast = tree.body[0]
    if not isinstance(func_ast, ast.FunctionDef):
        raise ValueError("Lean4 export source is not a function definition")

    try:
        from typing import get_type_hints

        hints = get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}

    param_names = [arg.arg for arg in func_ast.args.args]
    param_types: dict[str, type] = {}
    param_vars: dict[str, Any] = {}
    for name in param_names:
        typ = hints.get(name, float)
        param_types[name] = typ
        param_vars[name] = make_z3_var(name, typ)

    param_list = [param_vars[n] for n in param_names]
    pre_strs: list[str] = []
    post_strs: list[str] = []

    # Soundness: the exporter must refuse to emit an incomplete theorem
    # when the user's pre/post raises. A silently-dropped pre becomes a
    # Lean theorem stronger than the user asked for, which will either
    # fail to type-check (OK) or type-check spuriously if the post is
    # trivially true (NOT OK).
    if pre is not None:
        try:
            pre_z3 = pre(*param_list)
        except Exception as e:  # noqa: BLE001 — re-raised as ValueError
            raise ValueError(f"Precondition raised when exporting: {e}") from e
        if not isinstance(pre_z3, _z3.BoolRef):
            raise ValueError("Precondition must produce a symbolic Boolean expression")
        pre_strs.append(str(pre_z3))

    for name, var in param_vars.items():
        typ = hints.get(name)
        if typ is not None:
            for constraint in extract_refinements(typ, var):
                pre_strs.append(str(constraint))

    if post is not None:
        result_type = hints.get("return", float)
        try:
            result_var = make_z3_var("result", result_type)
        except TypeError as e:
            raise ValueError(f"Unsupported return type when exporting: {e}") from e
        try:
            post_z3 = post(*param_list, result_var)
        except Exception as e:  # noqa: BLE001 — re-raised as ValueError
            raise ValueError(f"Postcondition raised when exporting: {e}") from e
        if not isinstance(post_z3, _z3.BoolRef):
            raise ValueError("Postcondition must produce a symbolic Boolean expression")
        post_strs.append(str(post_z3))

    pre_lean = (
        " ∧ ".join(f"({_z3_str_to_lean(s, param_names)})" for s in pre_strs) if pre_strs else None
    )
    post_lean = (
        " ∧ ".join(f"({_z3_str_to_lean(s, param_names)})" for s in post_strs)
        if post_strs
        else None
    )

    if post_lean:
        post_lean = post_lean.replace("result", f"({fname}_impl {' '.join(param_names)})")

    lean_code = generate_lean4_theorem(
        func_name=fname,
        param_names=param_names,
        param_types=param_types,
        pre_str=pre_lean,
        post_str=post_lean,
        source=source,
    )

    if _contains_placeholder(lean_code):
        raise ValueError("Lean4 export contains an admitted placeholder")

    if output_path is not None:
        Path(output_path).write_text(lean_code)

    return lean_code
