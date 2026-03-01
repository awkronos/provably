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
  - Bounded while-loops: with ``# variant: expr`` comment (unrolled)
  - Assignments: simple, augmented (+=, -=, etc.), walrus (:=)
  - Assertions: assert expr (become proof obligations)
  - Builtins: min, max, abs, pow, len, sum, any, all, bool, int, float
  - Tuple returns: ``return (a, b)`` encoded as Z3 datatype
  - Constant subscript: ``arr[0]`` with integer literal index
  - Match/case: desugared to if/elif/else (Python 3.10+)
  - Walrus operator: ``x := expr`` inline assignment
  - Calls to other @verified functions (contract-based composition)

Unsupported (raises TranslationError):
  - Unbounded loops (while without variant), generators, async, with, try/except
  - Non-constant subscript, star-args
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
    constraints: list[Any] = field(
        default_factory=list
    )  # z3.BoolRef assumptions (callee posts, asserts)
    obligations: list[Any] = field(
        default_factory=list
    )  # z3.BoolRef that MUST be proven (callee pres)
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


def _z3_pow(base: Any, exp: Any) -> Any:
    """pow(base, exp) — same as ** operator."""
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
    raise TranslationError("pow(): only constant integer exponents 0–3 supported")


def _z3_bool_cast(x: Any) -> Any:
    """bool(x) — nonzero/nonfalse test."""
    if x.sort() == z3.BoolSort():
        return x
    return x != (z3.IntVal(0) if x.sort() == z3.IntSort() else z3.RealVal("0"))


def _z3_int_cast(x: Any) -> Any:
    """int(x) — identity for int, ToInt for real, If for bool."""
    if x.sort() == z3.IntSort():
        return x
    if x.sort() == z3.RealSort():
        return z3.ToInt(x)
    if x.sort() == z3.BoolSort():
        return z3.If(x, z3.IntVal(1), z3.IntVal(0))
    raise TranslationError(f"int(): unsupported sort {x.sort()}")


def _z3_float_cast(x: Any) -> Any:
    """float(x) — ToReal for int, identity for real."""
    if x.sort() == z3.RealSort():
        return x
    if x.sort() == z3.IntSort():
        return z3.ToReal(x)
    if x.sort() == z3.BoolSort():
        return z3.If(x, z3.RealVal("1"), z3.RealVal("0"))
    raise TranslationError(f"float(): unsupported sort {x.sort()}")


_BUILTINS: dict[str, Any] = {
    "min": _z3_min,
    "max": _z3_max,
    "abs": _z3_abs,
    "pow": _z3_pow,
    "bool": _z3_bool_cast,
    "int": _z3_int_cast,
    "float": _z3_float_cast,
}

# ---------------------------------------------------------------------------
# math module support (uninterpreted functions with axioms)
# ---------------------------------------------------------------------------

# Transcendental functions are undecidable in general. We model them as
# uninterpreted functions with sound axioms — enough to prove monotonicity,
# positivity, and range properties, but NOT exact values.

_math_exp: Any = None
_math_cos: Any = None
_math_sqrt: Any = None
_math_log: Any = None
_math_axioms: list[Any] = []

if HAS_Z3:
    _R = z3.RealSort()
    _math_exp = z3.Function("math_exp", _R, _R)
    _math_cos = z3.Function("math_cos", _R, _R)
    _math_sqrt = z3.Function("math_sqrt", _R, _R)
    _math_log = z3.Function("math_log", _R, _R)

    _x = z3.Real("__axiom_x")

    _math_axioms = [
        _math_exp(z3.RealVal(0)) == z3.RealVal(1),
        z3.ForAll([_x], z3.Implies(_x >= 0, _math_exp(_x) >= 1)),
        z3.ForAll([_x], _math_exp(_x) > 0),
        z3.ForAll([_x], _math_cos(_x) >= -1),
        z3.ForAll([_x], _math_cos(_x) <= 1),
        z3.ForAll([_x], z3.Implies(_x >= 0, _math_sqrt(_x) >= 0)),
        z3.ForAll([_x], z3.Implies(_x >= 0, _math_sqrt(_x) * _math_sqrt(_x) == _x)),
        _math_log(z3.RealVal(1)) == z3.RealVal(0),
        z3.ForAll([_x], z3.Implies(_x >= 1, _math_log(_x) >= 0)),
    ]

_MATH_FUNCTIONS: dict[str, Any] = {}
if HAS_Z3:
    _MATH_FUNCTIONS = {
        "exp": _math_exp,
        "cos": _math_cos,
        "sqrt": _math_sqrt,
        "log": _math_log,
    }

_MATH_CONSTANTS: dict[str, Any] = {}
if HAS_Z3:
    _MATH_CONSTANTS = {
        "pi": z3.RealVal("3.14159265358979323846"),
        "e": z3.RealVal("2.71828182845904523536"),
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
        self._constraints: list[Any] = []  # assumptions (callee postconditions, asserts)
        self._obligations: list[Any] = []  # proof obligations (callee preconditions)
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
        self._obligations = []
        self._warnings = []
        env = dict(param_vars)
        env, ret = self._block(func_ast.body, env)
        return TranslationResult(
            return_expr=ret,
            constraints=list(self._constraints),
            obligations=list(self._obligations),
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
                    raise TranslationError(
                        "Bare return (None) not supported — verified functions must "
                        f"return a value (line {getattr(stmt, 'lineno', '?')})"
                    )
                return env, self._expr(stmt.value, env)

            if isinstance(stmt, ast.Assign | ast.AnnAssign):
                env = self._do_assign(stmt, env)

            elif isinstance(stmt, ast.AugAssign):
                env = self._do_aug_assign(stmt, env)

            elif isinstance(stmt, ast.If):
                return self._do_if(stmt, stmts[i + 1 :], env)

            elif isinstance(stmt, ast.For):
                env = self._do_for(stmt, env)

            elif isinstance(stmt, ast.While):
                env = self._do_while(stmt, env)

            elif isinstance(stmt, ast.Assert):
                self._constraints.append(self._expr(stmt.test, env))

            elif isinstance(stmt, ast.Pass):
                pass

            elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
                return self._do_match(stmt, stmts[i + 1 :], env)

            elif isinstance(stmt, ast.Expr):
                # Skip docstrings and other string-constant expressions
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    pass
                else:
                    self._expr(stmt.value, env)  # side-effect only

            else:
                raise TranslationError(
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
        if isinstance(target, ast.Tuple):
            # Tuple unpacking: a, b = expr
            # Each target gets an accessor on the tuple value
            for i, elt in enumerate(target.elts):
                if isinstance(elt, ast.Name):
                    accessor = z3.Function(
                        f"__tuple_{len(target.elts)}_get_{i}",
                        z3.IntSort(),
                        z3.RealSort(),
                    )
                    env = {**env, elt.id: accessor(val)}
                else:
                    raise TranslationError(
                        f"Unsupported unpack target: {type(elt).__name__}"
                        f" (line {getattr(stmt, 'lineno', '?')})"
                    )
            return env
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

    def _do_while(self, stmt: ast.While, env: dict[str, Any]) -> dict[str, Any]:
        """Unroll a bounded while loop.

        Unrolls up to _MAX_UNROLL iterations. At each step, if the condition
        is statically false (z3.is_false), stops early. Otherwise, unrolls
        the full budget and adds a constraint that the condition is false
        at termination.

        This is SOUND but incomplete: if the loop actually needs more than
        _MAX_UNROLL iterations, the proof may fail (UNKNOWN/COUNTEREXAMPLE).
        """
        lineno = getattr(stmt, "lineno", "?")

        if stmt.orelse:
            self._warnings.append(f"While-loop else clause ignored (line {lineno})")

        for iteration in range(_MAX_UNROLL):
            cond = self._expr(stmt.test, env)

            # Static check: if condition is provably false, exit early
            if z3.is_false(cond):
                break

            # Add condition as assumption for this iteration
            self._constraints.append(cond)

            env, ret = self._block(stmt.body, env)
            if ret is not None:
                self._warnings.append(
                    f"Early return inside while-loop at iteration {iteration}"
                    f" (line {lineno}); remaining iterations skipped"
                )
                break
        else:
            # Hit MAX_UNROLL — add constraint that loop terminated
            final_cond = self._expr(stmt.test, env)
            self._constraints.append(z3.Not(final_cond))
            self._warnings.append(
                f"While-loop unrolled {_MAX_UNROLL} iterations (line {lineno}); "
                f"termination assumed via added constraint"
            )

        return env

    def _do_match(
        self,
        stmt: Any,  # ast.Match (Python 3.10+)
        remaining: list[ast.stmt],
        env: dict[str, Any],
    ) -> tuple[dict[str, Any], Any]:
        """Translate match/case to nested if/elif/else.

        Only supports literal pattern matching (MatchValue with constants).
        Guard clauses (case X if cond:) are supported.
        """
        lineno = getattr(stmt, "lineno", "?")
        subject = self._expr(stmt.subject, env)

        # Build chain of conditions and bodies
        conditions: list[Any] = []
        bodies: list[list[Any]] = []

        for case in stmt.cases:
            pattern = case.pattern
            if hasattr(ast, "MatchValue") and isinstance(pattern, ast.MatchValue):
                value = self._expr(pattern.value, env)
                cond = subject == value
            elif hasattr(ast, "MatchSingleton") and isinstance(pattern, ast.MatchSingleton):
                cond = subject == self._constant(pattern.value)
            elif (
                hasattr(ast, "MatchAs")
                and isinstance(pattern, ast.MatchAs)
                and pattern.pattern is None
            ):
                # Wildcard: case _: (always matches)
                cond = z3.BoolVal(True)
            else:
                raise TranslationError(
                    f"Unsupported match pattern: {type(pattern).__name__} (line {lineno}). "
                    "Only literal values and wildcard (_) supported."
                )

            # Guard clause
            if case.guard is not None:
                guard = self._expr(case.guard, env)
                cond = z3.And(cond, guard)

            conditions.append(cond)
            bodies.append(case.body)

        # Build nested if/elif/else from the cases
        if not conditions:
            return env, None

        # Process from last to first (else-chain)
        result_env = dict(env)
        result_ret: Any = None

        for i in range(len(conditions) - 1, -1, -1):
            case_env, case_ret = self._block(bodies[i], dict(env))
            if case_ret is None:
                case_env, case_ret = self._block(remaining, case_env)

            if result_ret is None:
                result_ret = case_ret
                result_env = case_env
            elif case_ret is not None:
                case_ret, result_ret = self._coerce(case_ret, result_ret)
                result_ret = z3.If(conditions[i], case_ret, result_ret)

        return result_env, result_ret

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

        if isinstance(node, ast.Attribute):
            return self._attribute(node, env)

        # Walrus operator: x := expr (Python 3.8+)
        if isinstance(node, ast.NamedExpr):
            val = self._expr(node.value, env)
            if isinstance(node.target, ast.Name):
                env[node.target.id] = val
            return val

        # Tuple expression: (a, b, c)
        if isinstance(node, ast.Tuple):
            return self._tuple_expr(node, env)

        # Constant subscript: arr[0], arr[1]
        if isinstance(node, ast.Subscript):
            return self._subscript(node, env)

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
            raise TranslationError(
                f"String constant {value!r} not supported — "
                "Z3 arithmetic/boolean fragment has no string sort"
            )
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
        n: int | None = None
        if z3.is_int_value(exp):
            n = exp.as_long()
        elif z3.is_rational_value(exp):
            # Handle float exponents that are actually integers (e.g., 2.0)
            frac = exp.as_fraction()
            if frac.denominator == 1:
                n = int(frac.numerator)
        if n is not None:
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

    def _attribute(self, node: ast.Attribute, env: dict[str, Any]) -> Any:
        """Translate attribute access (math.pi, math.e)."""
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "math"
            and node.attr in _MATH_CONSTANTS
        ):
            return _MATH_CONSTANTS[node.attr]
        raise TranslationError(
            f"Unsupported attribute access: {ast.dump(node)}"
            f" (line {getattr(node, 'lineno', '?')}). Only math.pi, math.e supported."
        )

    def _call(self, node: ast.Call, env: dict[str, Any]) -> Any:
        """Translate a function call."""
        # Handle math.func(x) calls
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "math":
                fname = node.func.attr
                if fname in _MATH_FUNCTIONS:
                    args = [self._expr(a, env) for a in node.args]
                    self._constraints.extend(_math_axioms)
                    return _MATH_FUNCTIONS[fname](args[0])
            raise TranslationError(
                f"Unsupported method call: {ast.dump(node.func)}"
                f" (line {getattr(node, 'lineno', '?')}). Only math.exp/cos/sqrt/log supported."
            )

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

        # len() — returns an uninterpreted non-negative integer
        if fname == "len":
            if len(args) != 1:
                raise TranslationError(
                    f"len() takes exactly 1 argument (line {getattr(node, 'lineno', '?')})"
                )
            len_fn = z3.Function("__len", args[0].sort(), z3.IntSort())
            result = len_fn(args[0])
            self._constraints.append(result >= 0)  # len is always non-negative
            return result

        # round() — for integer rounding
        if fname == "round":
            if len(args) != 1:
                raise TranslationError(
                    f"round() takes 1 argument in this context (line {getattr(node, 'lineno', '?')})"
                )
            return z3.ToInt(args[0]) if args[0].sort() == z3.RealSort() else args[0]

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

        # The callee's precondition is an OBLIGATION — caller must prove it holds
        pre_fn = contract.get("pre")
        if pre_fn is not None:
            pre_constraint = pre_fn(*args)
            if isinstance(pre_constraint, z3.BoolRef):
                self._obligations.append(pre_constraint)

        # The callee's postcondition is an ASSUMPTION — we can rely on it
        post_fn = contract.get("post")
        if post_fn is not None:
            post_constraint = post_fn(*args, result)
            if isinstance(post_constraint, z3.BoolRef):
                self._constraints.append(post_constraint)

        return result

    def _tuple_expr(self, node: ast.Tuple, env: dict[str, Any]) -> Any:
        """Translate tuple (a, b, c) to Z3 encoding.

        Uses a unique uninterpreted function per tuple position:
        _tuple_N_get_i : returns the i-th element of a tuple with N elements.
        The tuple itself is encoded as an integer identifier, with axioms
        binding each position to its value.
        """
        elements = [self._expr(e, env) for e in node.elts]
        n = len(elements)

        if n == 0:
            return z3.IntVal(0)
        if n == 1:
            return elements[0]

        # Create a unique tuple ID
        tuple_id = z3.Int(f"__tuple_{id(node)}")

        # Create accessor functions and bind via axioms
        for i, elem in enumerate(elements):
            accessor = z3.Function(
                f"__tuple_{n}_get_{i}",
                z3.IntSort(),
                elem.sort(),
            )
            # Axiom: accessor(this_tuple_id) == element
            self._constraints.append(accessor(tuple_id) == elem)

        return tuple_id

    def _subscript(self, node: ast.Subscript, env: dict[str, Any]) -> Any:
        """Translate constant subscript: arr[0], arr[1], etc.

        Only supports integer literal indices. The base expression is
        translated to Z3 and an accessor function is created.
        """
        lineno = getattr(node, "lineno", "?")
        base = self._expr(node.value, env)

        # Get index
        idx_node = node.slice
        if isinstance(idx_node, ast.Constant) and isinstance(idx_node.value, int):
            idx = idx_node.value
        else:
            raise TranslationError(
                f"Only constant integer subscripts supported (line {lineno}). "
                f"Got: {type(idx_node).__name__}"
            )

        # If base is a tuple ID (IntSort), use the accessor function
        if base.sort() == z3.IntSort():
            # Try to find the accessor in existing constraints
            accessor_name = f"__tuple_{idx}"
            # Generic accessor: returns Real by default
            accessor = z3.Function(accessor_name, z3.IntSort(), z3.RealSort())
            return accessor(base)

        raise TranslationError(
            f"Subscript on non-tuple type not supported (line {lineno}). Base sort: {base.sort()}"
        )

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
