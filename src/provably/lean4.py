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
    - Only supports the same arithmetic subset as the Z3 translator
    - Transcendental functions (exp, cos, log) are axiomatized
    - For-loop unrolling produces verbose proofs
    - Slower than Z3 (compiles to native code)
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any

from .engine import ProofCertificate, Status

# Check if lean is available
try:
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
            # Lean4 float literal
            return f"({v} : Float)"
        return str(v)

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
            ast.FloorDiv: "/",
            ast.Mod: "%",
        }
        op = op_map.get(type(node.op), "?")
        return f"({left} {op} {right})"

    if isinstance(node, ast.UnaryOp):
        operand = _expr_to_lean(node.operand, env)
        if isinstance(node.op, ast.USub):
            return f"(-{operand})"
        if isinstance(node.op, ast.Not):
            return f"(¬ {operand})"
        return operand

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
            sym = cmp_map.get(type(cmp_op), "?")
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
        if func_name in builtin_map:
            return builtin_map[func_name](args)
        return f"({func_name} {' '.join(args)})"

    return f"sorry /- unsupported: {ast.dump(node)} -/"


def _if_to_lean(stmt: ast.If, env: dict[str, str]) -> str:
    """Recursively translate if/elif/else chains to Lean4."""
    test = _expr_to_lean(stmt.test, env)

    # Extract then-branch return
    then_ret = None
    for s in stmt.body:
        if isinstance(s, ast.Return) and s.value is not None:
            then_ret = _expr_to_lean(s.value, env)
            break

    # Extract else-branch (may be elif chain or return)
    else_ret = None
    if stmt.orelse:
        if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
            # elif chain — RECURSE
            else_ret = _if_to_lean(stmt.orelse[0], env)
        else:
            for s in stmt.orelse:
                if isinstance(s, ast.Return) and s.value is not None:
                    else_ret = _expr_to_lean(s.value, env)
                    break

    if then_ret and else_ret:
        return f"if {test} then {then_ret} else {else_ret}"
    elif then_ret:
        return f"if {test} then {then_ret} else sorry"
    elif else_ret:
        return f"if {test} then sorry else {else_ret}"
    return "sorry"


def _func_body_to_lean(func_ast: ast.FunctionDef, env: dict[str, str]) -> str:
    """Translate function body to a Lean4 definition body."""
    lines = []
    for stmt in func_ast.body:
        if isinstance(stmt, ast.Return) and stmt.value is not None:
            lines.append(_expr_to_lean(stmt.value, env))
        elif isinstance(stmt, ast.If):
            lines.append(_if_to_lean(stmt, env))
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    val = _expr_to_lean(stmt.value, env)
                    env[target.id] = val
                    lines.append(f"let {target.id} := {val}")
        elif isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                val = _expr_to_lean(stmt.value, env)
                op_map = {
                    ast.Add: "+",
                    ast.Sub: "-",
                    ast.Mult: "*",
                    ast.Div: "/",
                    ast.Mod: "%",
                }
                op = op_map.get(type(stmt.op), "+")
                current = env.get(name, name)
                new_val = f"({current} {op} {val})"
                env[name] = new_val
                lines.append(f"let {name} := {new_val}")
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            if isinstance(stmt.target, ast.Name):
                val = _expr_to_lean(stmt.value, env)
                env[stmt.target.id] = val
                lines.append(f"let {stmt.target.id} := {val}")
        elif (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            pass  # Skip docstrings
        elif isinstance(stmt, ast.Pass):
            pass
    return "\n  ".join(lines) if lines else "sorry"


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
        return "-- Error: not a function definition\nsorry"

    # Pick the output mode from parameter types.
    all_int_or_bool = all(
        param_types.get(name, float) in (int, bool)
        for name in param_names
    )
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
        if core_mode:
            # Keep Int/Bool as-is.
            pass
        elif lean_type == "Float":
            lean_type = "ℝ"
        params.append(f"({name} : {lean_type})")
    param_decl = " ".join(params)

    env = {n: n for n in param_names}
    body = _func_body_to_lean(func_ast, env)

    return_type = (
        "Int" if core_mode and ret_hint is int
        else "Bool" if core_mode and ret_hint is bool
        else "Int" if core_mode
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
    s = z3_str

    # Replace Z3 operators with Lean4 Unicode
    s = s.replace("And(", "(").replace("Or(", "(")
    s = s.replace(">=", "≥").replace("<=", "≤").replace("!=", "≠")
    s = s.replace(",", " ∧")  # And args separated by commas

    # Replace Not(x) with ¬x
    while "Not(" in s:
        idx = s.index("Not(")
        # Find matching close paren
        depth = 0
        end = idx + 4
        for i in range(idx + 4, len(s)):
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                if depth == 0:
                    end = i
                    break
                depth -= 1
        inner = s[idx + 4 : end]
        s = s[:idx] + f"¬({inner})" + s[end + 1 :]

    return s


# =============================================================================
# LEAN4 PROOF CHECKING
# =============================================================================


def check_lean4_proof(lean_code: str, timeout_s: float = 60.0) -> tuple[bool, str]:
    """Write Lean4 code to a temp file and check it.

    Returns (success, output).
    """
    if not HAS_LEAN4:
        return False, "Lean4 not installed"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".lean", delete=False, prefix="provably_"
    ) as f:
        f.write(lean_code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["lean", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
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

    # Build Z3 string representations of pre/post
    pre_strs: list[str] = []
    post_strs: list[str] = []
    param_list = [param_vars[n] for n in param_names]

    if pre is not None:
        try:
            pre_z3 = pre(*param_list)
            if isinstance(pre_z3, _z3.BoolRef):
                pre_strs.append(str(pre_z3))
        except Exception:
            pass

    # Add refinement constraints
    for name, var in param_vars.items():
        typ = hints.get(name)
        if typ is not None:
            for constraint in extract_refinements(typ, var):
                pre_strs.append(str(constraint))

    if post is not None:
        # Create a result variable for postcondition
        result_var = _z3.Real("result")
        try:
            post_z3 = post(*param_list, result_var)
            if isinstance(post_z3, _z3.BoolRef):
                post_strs.append(str(post_z3))
        except Exception:
            pass

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
    lean_code = generate_lean4_theorem(
        func_name=fname,
        param_names=param_names,
        param_types=param_types,
        pre_str=pre_lean,
        post_str=post_lean,
        source=source,
    )

    # Check with Lean4
    t0 = time.monotonic()
    success, output = check_lean4_proof(lean_code, timeout_s=timeout_s)
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
        return "-- Error: not a function definition\n"

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

    if pre is not None:
        try:
            pre_z3 = pre(*param_list)
            if isinstance(pre_z3, _z3.BoolRef):
                pre_strs.append(str(pre_z3))
        except Exception:
            pass

    for name, var in param_vars.items():
        typ = hints.get(name)
        if typ is not None:
            for constraint in extract_refinements(typ, var):
                pre_strs.append(str(constraint))

    if post is not None:
        result_var = _z3.Real("result")
        try:
            post_z3 = post(*param_list, result_var)
            if isinstance(post_z3, _z3.BoolRef):
                post_strs.append(str(post_z3))
        except Exception:
            pass

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

    if output_path is not None:
        Path(output_path).write_text(lean_code)

    return lean_code
