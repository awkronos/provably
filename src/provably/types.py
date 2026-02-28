"""Refinement types and Z3 sort mapping for Provably.

Maps Python type annotations to Z3 sorts, and provides refinement type
markers compatible with typing.Annotated for embedding proof obligations
directly in function signatures.

Convenience aliases
-------------------
``Positive``     — ``Annotated[float, Gt(0)]``
``NonNegative``  — ``Annotated[float, Ge(0)]``
``UnitInterval`` — ``Annotated[float, Between(0, 1)]``

These compose with other annotations::

    x: Annotated[Positive, Le(100)]  # 0 < x <= 100
"""

from __future__ import annotations

from typing import Any, get_args, get_origin, Annotated

try:
    import z3

    HAS_Z3 = True
except ImportError:
    z3 = None  # type: ignore[assignment]
    HAS_Z3 = False


# ---------------------------------------------------------------------------
# Python type → Z3 sort
# ---------------------------------------------------------------------------

def python_type_to_z3_sort(typ: type) -> Any:
    """Map a Python type annotation to a Z3 sort.

    Strips ``Annotated`` wrappers and maps ``int`` → ``IntSort``,
    ``float`` → ``RealSort``, ``bool`` → ``BoolSort``.

    Args:
        typ: A Python type, optionally wrapped in ``Annotated``.

    Returns:
        The corresponding Z3 sort.

    Raises:
        RuntimeError: If z3-solver is not installed.
        TypeError: If no Z3 sort exists for the given type.
    """
    if not HAS_Z3:
        raise RuntimeError("z3-solver is required for type mapping")

    origin = get_origin(typ)
    if origin is Annotated:
        return python_type_to_z3_sort(get_args(typ)[0])

    _MAP: dict[type, Any] = {
        int: z3.IntSort(),
        float: z3.RealSort(),
        bool: z3.BoolSort(),
    }
    sort = _MAP.get(typ)
    if sort is not None:
        return sort
    raise TypeError(f"No Z3 sort for Python type: {typ}")


def make_z3_var(name: str, typ: type) -> Any:
    """Create a Z3 variable from a name and Python type annotation.

    Args:
        name: The variable name (used as the Z3 symbol name).
        typ: The Python type annotation (``int``, ``float``, ``bool``,
             or ``Annotated`` wrappers of these).

    Returns:
        A Z3 ``Int``, ``Real``, or ``Bool`` variable.

    Raises:
        RuntimeError: If z3-solver is not installed.
        TypeError: If the type cannot be mapped to a Z3 sort.
    """
    if not HAS_Z3:
        raise RuntimeError("z3-solver is required")

    sort = python_type_to_z3_sort(typ)
    if sort == z3.IntSort():
        return z3.Int(name)
    if sort == z3.RealSort():
        return z3.Real(name)
    if sort == z3.BoolSort():
        return z3.Bool(name)
    raise TypeError(f"Cannot create Z3 variable for sort: {sort}")


# ---------------------------------------------------------------------------
# Refinement markers — use with typing.Annotated
#
#   x: Annotated[float, Ge(0), Le(1)]   →   0 ≤ x ≤ 1
#   x: Annotated[int, Between(1, 100)]  →   1 ≤ x ≤ 100
# ---------------------------------------------------------------------------

class Gt:
    """Strictly greater than a bound.

    Example::

        x: Annotated[float, Gt(0)]   # x > 0  (strictly positive)
    """

    __slots__ = ("bound",)

    def __init__(self, bound: int | float) -> None:
        self.bound = bound

    def __repr__(self) -> str:
        return f"Gt({self.bound})"


class Ge:
    """Greater than or equal to a bound.

    Example::

        x: Annotated[float, Ge(0)]   # x >= 0  (non-negative)
    """

    __slots__ = ("bound",)

    def __init__(self, bound: int | float) -> None:
        self.bound = bound

    def __repr__(self) -> str:
        return f"Ge({self.bound})"


class Lt:
    """Strictly less than a bound.

    Example::

        x: Annotated[float, Lt(1)]   # x < 1
    """

    __slots__ = ("bound",)

    def __init__(self, bound: int | float) -> None:
        self.bound = bound

    def __repr__(self) -> str:
        return f"Lt({self.bound})"


class Le:
    """Less than or equal to a bound.

    Example::

        x: Annotated[float, Le(1)]   # x <= 1
    """

    __slots__ = ("bound",)

    def __init__(self, bound: int | float) -> None:
        self.bound = bound

    def __repr__(self) -> str:
        return f"Le({self.bound})"


class Between:
    """Inclusive range [lo, hi].

    Example::

        x: Annotated[float, Between(0, 1)]   # 0 <= x <= 1
        n: Annotated[int, Between(1, 100)]   # 1 <= n <= 100
    """

    __slots__ = ("lo", "hi")

    def __init__(self, lo: int | float, hi: int | float) -> None:
        self.lo = lo
        self.hi = hi

    def __repr__(self) -> str:
        return f"Between({self.lo}, {self.hi})"


class NotEq:
    """Not equal to a value.

    Example::

        x: Annotated[float, NotEq(0)]   # x != 0  (non-zero divisor)
    """

    __slots__ = ("val",)

    def __init__(self, val: int | float) -> None:
        self.val = val

    def __repr__(self) -> str:
        return f"NotEq({self.val})"


def extract_refinements(typ: type, var: Any) -> list[Any]:
    """Extract Z3 constraints from ``Annotated`` type markers.

    Walks the metadata arguments of an ``Annotated`` type and converts
    each ``Gt`` / ``Ge`` / ``Lt`` / ``Le`` / ``Between`` / ``NotEq``
    marker into a Z3 ``BoolRef`` constraint on *var*.

    Also supports callable markers: ``marker(var)`` is called and the
    result is included if it is a ``z3.BoolRef``.

    Args:
        typ: A Python type, typically ``Annotated[base, *markers]``.
        var: The Z3 variable to constrain.

    Returns:
        A list of ``z3.BoolRef`` constraints. Empty if z3 is not
        installed or if *typ* is not ``Annotated``.
    """
    if not HAS_Z3:
        return []

    origin = get_origin(typ)
    if origin is not Annotated:
        return []

    args = get_args(typ)
    constraints: list[Any] = []
    for marker in args[1:]:
        if isinstance(marker, Gt):
            constraints.append(var > marker.bound)
        elif isinstance(marker, Ge):
            constraints.append(var >= marker.bound)
        elif isinstance(marker, Lt):
            constraints.append(var < marker.bound)
        elif isinstance(marker, Le):
            constraints.append(var <= marker.bound)
        elif isinstance(marker, Between):
            constraints.append(var >= marker.lo)
            constraints.append(var <= marker.hi)
        elif isinstance(marker, NotEq):
            constraints.append(var != marker.val)
        elif get_origin(marker) is Annotated:
            # Nested Annotated type (e.g., Positive = Annotated[float, Gt(0)])
            constraints.extend(extract_refinements(marker, var))
        elif callable(marker) and not isinstance(marker, type):
            # Custom predicate callable (but not a bare type like float/int)
            try:
                result = marker(var)
                if HAS_Z3 and isinstance(result, z3.BoolRef):
                    constraints.append(result)
            except (TypeError, Exception):
                pass  # Not a valid constraint callable
    return constraints


# ---------------------------------------------------------------------------
# Convenience type aliases
# ---------------------------------------------------------------------------

#: ``float`` that is strictly greater than zero (``x > 0``).
Positive = Annotated[float, Gt(0)]

#: ``float`` that is greater than or equal to zero (``x >= 0``).
NonNegative = Annotated[float, Ge(0)]

#: ``float`` in the closed unit interval ``[0, 1]`` (``0 <= x <= 1``).
UnitInterval = Annotated[float, Between(0, 1)]
