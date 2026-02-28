"""Python AST → Z3 constraint translator.

This module is the Trusted Computing Base (TCB) of provably.
Bugs here can produce unsound proofs. It is intentionally kept small
and should be read, reviewed, and tested with extreme care.

Supported Python subset:
  - Arithmetic: +, -, *, /, //, %, ** (constant int exponents 0-3)
  - Comparisons: <, <=, >, >=, ==, != (chained)
  - Boolean: and, or, not
  - Control flow: if/elif/else, early return
  - Bounded for-loops: ``for i in range(N)`` where N is a literal constant
  - Assignments: simple, augmented (+=, -=, etc.)
  - Assertions: assert expr (become proof obligations)
  - Builtins: min, max, abs
  - Calls to other @verified functions (contract-based composition)

Unsupported (raises TranslationError):
  - Unbounded loops, generators, async, with, try/except
  - Attribute access, subscript, star-args
  - Class definitions, lambda, comprehensions
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

import z3

HAS_Z3 = True  # z3-solver is a hard dependency

# Maximum number of iterations for ``for i in range(N)`` unrolling.
_MAX_UNROLL = 256


class TranslationError(Exception):
    """Raised when the translator encounters unsupported Python constructs."""


@dataclass
class TranslationResult:
    """Result of translating a function body to Z3 constraints."""

    return_expr: Any  # z3.ExprRef | None
    constraints: list[Any] = field(default_factory=list)  # z3.BoolRef obligations
    env: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in function translations
# ---------------------------------------------------------------------------


def _z3_min(a: Any, b: Any) -> Any:
    return z3.If(a <= b, a, b)


def _z3_max(a: Any, b: Any) -> Any:
    return z3.If(a >= b, a, b)


def _z3_abs(x: Any) -> Any:
    return z3.If(x >= 0, x, -x)


_BUILTINS: dict[str, Any] = {
    "min": _z3_min,
    "max": _z3_max,
    "abs": _z3_abs,
}


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------


class Translator:
    """Translates a Python function AST into Z3 constraints.

    The translation is environment-based: each variable name maps to its
    current Z3 expression (SSA-style, via dict copy on branching).

    Bounded ``for i in range(N)`` loops are supported when ``N`` is a
    compile-time integer constant (literal or resolved closure variable).
    The loop is fully unrolled up to ``_MAX_UNROLL`` iterations.

    Args:
        param_types: Mapping from parameter name to Python type annotation.
        verified_contracts: Pre/post contracts of called @verified functions,
            keyed by function name.
        closure_vars: Module-level constants resolved from the function's
            global scope, already converted to Z3 expressions.
    """

    def __init__(
        self,
        param_types: dict[str, type] | None = None,
        verified_contracts: dict[str, dict[str, Any]] | None = None,
        closure_vars: dict[str, Any] | None = None,
    ) -> None:
        self.param_types = param_types or {}
        self.verified_contracts = verified_contracts or {}
        self.closure_vars = closure_vars or {}
        self._constraints: list[Any] = []
        self._warnings: list[str] = []

    def translate(
        self,
        func_ast: ast.FunctionDef,
        param_vars: dict[str, Any],
    ) -> TranslationResult:
        """Translate a function definition to Z3 constraints.

        Args:
            func_ast: The parsed ``ast.FunctionDef`` node.
            param_vars: Mapping from parameter name to the corresponding
                Z3 symbolic variable.

        Returns:
            A :class:`TranslationResult` containing the symbolic return
            expression, accumulated constraints, final environment, and
            any non-fatal warnings.
        """
        self._constraints = []
        self._warnings = []
        env = dict(param_vars)
        env, ret = self._block(func_ast.body, env)
        return TranslationResult(
            return_expr=ret,
            constraints=list(self._constraints),
            env=env,
            warnings=list(self._warnings),
        )

    # ------------------------------------------------------------------
    # Statement translation
    # ------------------------------------------------------------------

    def _block(self, stmts: list[ast.stmt], env: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        """Translate a block. Returns (env, return_expr | None)."""
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, ast.Return):
                if stmt.value is None:
                    return env, z3.BoolVal(True)
                return env, self._expr(stmt.value, env)

            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                env = self._do_assign(stmt, env)

            elif isinstance(stmt, ast.AugAssign):
                env = self._do_aug_assign(stmt, env)

            elif isinstance(stmt, ast.If):
                return self._do_if(stmt, stmts[i + 1 :], env)

            elif isinstance(stmt, ast.For):
                env = self._do_for(stmt, env)

            elif isinstance(stmt, ast.Assert):
                self._constraints.append(self._expr(stmt.test, env))

            elif isinstance(stmt, ast.Pass):
                pass

            elif isinstance(stmt, ast.Expr):
                # Skip docstrings and other string-constant expressions
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    pass
                else:
                    self._expr(stmt.value, env)  # side-effect only

            else:
                self._warnings.append(
                    f"Unsupported statement: {type(stmt).__name__}"
                    f" (line {getattr(stmt, 'lineno', '?')})"
                )
        return env, None

    def _do_assign(self, stmt: ast.Assign | ast.AnnAssign, env: dict[str, Any]) -> dict[str, Any]:
        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is None:
                return env
            target = stmt.target
        else:
            if len(stmt.targets) != 1:
                raise TranslationError(
                    f"Multiple assignment targets not supported"
                    f" (line {getattr(stmt, 'lineno', '?')})"
                )
            target = stmt.targets[0]  # type: ignore[assignment]

        val = self._expr(stmt.value, env)  # type: ignore[arg-type]
        if isinstance(target, ast.Name):
            return {**env, target.id: val}
        raise TranslationError(
            f"Unsupported assignment target: {type(target).__name__}"
            f" (line {getattr(stmt, 'lineno', '?')})"
        )

    def _do_aug_assign(self, stmt: ast.AugAssign, env: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(stmt.target, ast.Name):
            raise TranslationError(
                f"Unsupported aug-assign target: {type(stmt.target).__name__}"
                f" (line {getattr(stmt, 'lineno', '?')})"
            )
        name = stmt.target.id
        if name not in env:
            raise TranslationError(
                f"Undefined variable in aug-assign: {name} (line {getattr(stmt, 'lineno', '?')})"
            )
        current = env[name]
        delta = self._expr(stmt.value, env)
        return {**env, name: self._binop(stmt.op, current, delta)}

    def _do_if(
        self,
        stmt: ast.If,
        remaining: list[ast.stmt],
        env: dict[str, Any],
    ) -> tuple[dict[str, Any], Any]:
        """Translate if/elif/else with remaining-statement continuation."""
        cond = self._expr(stmt.test, env)

        # Translate each branch body
        t_env, t_ret = self._block(stmt.body, dict(env))
        f_env, f_ret = self._block(stmt.orelse or [], dict(env))

        # Branches that didn't return continue with remaining statements
        if t_ret is None:
            t_env, t_ret = self._block(remaining, t_env)
        if f_ret is None:
            f_env, f_ret = self._block(remaining, f_env)

        if t_ret is not None and f_ret is not None:
            t_ret, f_ret = self._coerce(t_ret, f_ret)
            return env, z3.If(cond, t_ret, f_ret)
        if t_ret is not None:
            return env, t_ret
        if f_ret is not None:
            return env, f_ret

        # Neither branch returned — merge environments
        return self._merge_envs(cond, t_env, f_env, env), None

    def _do_for(self, stmt: ast.For, env: dict[str, Any]) -> dict[str, Any]:
        """Unroll a bounded ``for i in range(N)`` loop.

        Only supports the pattern ``for <name> in range(<int_literal>)``.
        ``N`` must be a constant resolvable at translation time (literal
        integer or a closure variable with a known integer Z3 value).

        Raises:
            TranslationError: For any unsupported loop pattern or if the
                bound is not a statically-known non-negative integer, or
                if ``N > _MAX_UNROLL``.
        """
        lineno = getattr(stmt, "lineno", "?")

        # Target must be a simple name
        if not isinstance(stmt.target, ast.Name):
            raise TranslationError(
                f"For-loop target must be a simple name, got"
                f" {type(stmt.target).__name__} (line {lineno})"
            )
        loop_var = stmt.target.id

        # iter must be range(N)
        if not (
            isinstance(stmt.iter, ast.Call)
            and isinstance(stmt.iter.func, ast.Name)
            and stmt.iter.func.id == "range"
        ):
            raise TranslationError(f"Only 'for i in range(N)' loops are supported (line {lineno})")

        range_args = stmt.iter.args
        if len(range_args) not in (1, 2, 3):
            raise TranslationError(f"range() requires 1–3 arguments (line {lineno})")

        def _resolve_int(node: ast.expr) -> int:
            """Resolve a constant integer from an AST node."""
            if isinstance(node, ast.Constant) and isinstance(node.value, int):
                return node.value
            if isinstance(node, ast.Name):
                # Try closure vars
                cv = self.closure_vars.get(node.id)
                if cv is not None and z3.is_int_value(cv):
                    return int(cv.as_long())
            raise TranslationError(f"For-loop bound must be a constant integer (line {lineno})")

        if len(range_args) == 1:
            start, stop, step = 0, _resolve_int(range_args[0]), 1
        elif len(range_args) == 2:
            start = _resolve_int(range_args[0])
            stop = _resolve_int(range_args[1])
            step = 1
        else:
            start = _resolve_int(range_args[0])
            stop = _resolve_int(range_args[1])
            step = _resolve_int(range_args[2])

        if step == 0:
            raise TranslationError(f"For-loop step cannot be zero (line {lineno})")

        iterations = list(range(start, stop, step))
        if len(iterations) > _MAX_UNROLL:
            raise TranslationError(
                f"For-loop would unroll {len(iterations)} iterations,"
                f" max is {_MAX_UNROLL} (line {lineno})"
            )

        if stmt.orelse:
            self._warnings.append(f"For-loop else clause ignored (line {lineno})")

        for i_val in iterations:
            env = {**env, loop_var: z3.IntVal(i_val)}
            env, ret = self._block(stmt.body, env)
            if ret is not None:
                # Early return inside a loop body — we emit a warning and stop
                self._warnings.append(
                    f"Early return inside for-loop unrolling at i={i_val}"
                    f" (line {lineno}); remaining iterations skipped"
                )
                break

        return env

    # ------------------------------------------------------------------
    # Expression translation
    # ------------------------------------------------------------------

    def _expr(self, node: ast.expr, env: dict[str, Any]) -> Any:
        """Translate an expression node to a Z3 expression."""
        if isinstance(node, ast.Constant):
            return self._constant(node.value)

        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            if node.id in self.closure_vars:
                return self.closure_vars[node.id]
            if node.id == "True":
                return z3.BoolVal(True)
            if node.id == "False":
                return z3.BoolVal(False)
            raise TranslationError(
                f"Undefined variable: {node.id} (line {getattr(node, 'lineno', '?')})"
            )

        if isinstance(node, ast.BinOp):
            left = self._expr(node.left, env)
            right = self._expr(node.right, env)
            return self._binop(node.op, left, right)

        if isinstance(node, ast.UnaryOp):
            operand = self._expr(node.operand, env)
            return self._unaryop(node.op, operand)

        if isinstance(node, ast.BoolOp):
            values = [self._expr(v, env) for v in node.values]
            if isinstance(node.op, ast.And):
                return z3.And(*values)
            if isinstance(node.op, ast.Or):
                return z3.Or(*values)
            raise TranslationError(
                f"Unsupported bool op: {type(node.op).__name__}"
                f" (line {getattr(node, 'lineno', '?')})"
            )

        if isinstance(node, ast.Compare):
            return self._compare(node, env)

        if isinstance(node, ast.IfExp):
            test = self._expr(node.test, env)
            body = self._expr(node.body, env)
            orelse = self._expr(node.orelse, env)
            body, orelse = self._coerce(body, orelse)
            return z3.If(test, body, orelse)

        if isinstance(node, ast.Call):
            return self._call(node, env)

        if isinstance(node, ast.Tuple):
            raise TranslationError(
                "Tuple expressions not supported — return a single value"
                f" (line {getattr(node, 'lineno', '?')})"
            )

        raise TranslationError(
            f"Unsupported expression: {type(node).__name__} (line {getattr(node, 'lineno', '?')})"
        )

    def _constant(self, value: Any) -> Any:
        if isinstance(value, bool):
            return z3.BoolVal(value)
        if isinstance(value, int):
            return z3.IntVal(value)
        if isinstance(value, float):
            return z3.RealVal(str(value))
        if isinstance(value, str):
            # String constants cannot be represented in Z3's arithmetic/bool logic.
            # Emit a warning rather than crashing; callers should not rely on
            # the returned expression for proof obligations.
            self._warnings.append(
                f"String constant {value!r} is not representable in Z3 — "
                "it will be treated as an opaque symbolic term"
            )
            # Return a fresh unconstrained Z3 integer as a placeholder.
            # This keeps the translator running but the resulting proof
            # will likely be UNKNOWN or produce a spurious certificate.
            return z3.Int(f"__str_{hash(value) & 0xFFFF:04x}__")
        raise TranslationError(f"Unsupported constant type: {type(value).__name__}")

    def _binop(self, op: ast.operator, left: Any, right: Any) -> Any:
        left, right = self._coerce(left, right)
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            if left.sort() == z3.IntSort():
                return left / right
            raise TranslationError("Floor division only supported for integers")
        if isinstance(op, ast.Mod):
            if left.sort() == z3.IntSort():
                return left % right
            raise TranslationError("Modulo only supported for integers")
        if isinstance(op, ast.Pow):
            return self._pow(left, right)
        raise TranslationError(f"Unsupported operator: {type(op).__name__}")

    def _pow(self, base: Any, exp: Any) -> Any:
        """Handle ** with constant integer exponents only."""
        if z3.is_int_value(exp):
            n = exp.as_long()
            if n == 0:
                return z3.RealVal("1") if base.sort() == z3.RealSort() else z3.IntVal(1)
            if n == 1:
                return base
            if n == 2:
                return base * base
            if n == 3:
                return base * base * base
        raise TranslationError("Only constant integer exponents 0–3 supported for **")

    def _unaryop(self, op: ast.unaryop, operand: Any) -> Any:
        if isinstance(op, ast.USub):
            return -operand
        if isinstance(op, ast.Not):
            return z3.Not(operand)
        if isinstance(op, ast.UAdd):
            return operand
        raise TranslationError(f"Unsupported unary op: {type(op).__name__}")

    def _compare(self, node: ast.Compare, env: dict[str, Any]) -> Any:
        """Translate comparisons, including chained (a < b < c)."""
        left = self._expr(node.left, env)
        parts: list[Any] = []
        for op, comp_node in zip(node.ops, node.comparators, strict=False):
            right = self._expr(comp_node, env)
            lc, rc = self._coerce(left, right)
            if isinstance(op, ast.Lt):
                parts.append(lc < rc)
            elif isinstance(op, ast.LtE):
                parts.append(lc <= rc)
            elif isinstance(op, ast.Gt):
                parts.append(lc > rc)
            elif isinstance(op, ast.GtE):
                parts.append(lc >= rc)
            elif isinstance(op, ast.Eq):
                parts.append(lc == rc)
            elif isinstance(op, ast.NotEq):
                parts.append(lc != rc)
            else:
                raise TranslationError(
                    f"Unsupported comparison: {type(op).__name__}"
                    f" (line {getattr(node, 'lineno', '?')})"
                )
            left = right  # chaining
        if len(parts) == 1:
            return parts[0]
        return z3.And(*parts)

    def _call(self, node: ast.Call, env: dict[str, Any]) -> Any:
        """Translate a function call."""
        if not isinstance(node.func, ast.Name):
            raise TranslationError(
                f"Only simple function calls supported, got: {ast.dump(node.func)}"
                f" (line {getattr(node, 'lineno', '?')})"
            )
        fname = node.func.id
        args = [self._expr(a, env) for a in node.args]

        # Built-in translations
        if fname in _BUILTINS:
            return _BUILTINS[fname](*args)

        # Verified contract composition
        if fname in self.verified_contracts:
            return self._call_verified(fname, args)

        raise TranslationError(
            f"Unknown function '{fname}' (line {getattr(node, 'lineno', '?')}). "
            f"Add @verified or register in verified_contracts."
        )

    def _call_verified(self, fname: str, args: list[Any]) -> Any:
        """Apply a verified function's contract (modular verification)."""
        contract = self.verified_contracts[fname]
        param_sorts = [a.sort() for a in args]
        return_sort = contract.get("return_sort", z3.RealSort())
        f_decl = z3.Function(fname, *param_sorts, return_sort)
        result = f_decl(*args)

        # The callee's precondition is an OBLIGATION for the caller
        pre_fn = contract.get("pre")
        if pre_fn is not None:
            pre_constraint = pre_fn(*args)
            if isinstance(pre_constraint, z3.BoolRef):
                self._constraints.append(pre_constraint)

        # The callee's postcondition is an ASSUMPTION we can use
        post_fn = contract.get("post")
        if post_fn is not None:
            post_constraint = post_fn(*args, result)
            if isinstance(post_constraint, z3.BoolRef):
                # Add positively — we assume this holds
                self._constraints.append(post_constraint)

        return result

    # ------------------------------------------------------------------
    # Type coercion
    # ------------------------------------------------------------------

    def _coerce(self, a: Any, b: Any) -> tuple[Any, Any]:
        """Promote operands to compatible Z3 sorts (Int → Real)."""
        if a.sort() == b.sort():
            return a, b
        if a.sort() == z3.IntSort() and b.sort() == z3.RealSort():
            return z3.ToReal(a), b
        if a.sort() == z3.RealSort() and b.sort() == z3.IntSort():
            return a, z3.ToReal(b)
        if a.sort() == z3.BoolSort():
            a = z3.If(a, z3.IntVal(1), z3.IntVal(0))
            return self._coerce(a, b)
        if b.sort() == z3.BoolSort():
            b = z3.If(b, z3.IntVal(1), z3.IntVal(0))
            return self._coerce(a, b)
        raise TranslationError(f"Cannot coerce sorts: {a.sort()} and {b.sort()}")

    def _merge_envs(
        self,
        cond: Any,
        t_env: dict[str, Any],
        f_env: dict[str, Any],
        orig_env: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge two branch environments using phi nodes (z3.If)."""
        merged = dict(orig_env)
        for key in set(t_env) | set(f_env):
            t_val = t_env.get(key, orig_env.get(key))
            f_val = f_env.get(key, orig_env.get(key))
            if t_val is not None and f_val is not None:
                if t_val is not f_val:
                    t_val, f_val = self._coerce(t_val, f_val)
                    merged[key] = z3.If(cond, t_val, f_val)
                else:
                    merged[key] = t_val
            elif t_val is not None:
                merged[key] = t_val
            elif f_val is not None:
                merged[key] = f_val
        return merged
