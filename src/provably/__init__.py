"""Provably — proof-carrying Python via Z3.

Annotate functions with contracts, get automatic formal proofs.

    from provably import verified, configure
    from provably.types import Ge, Le, Between, NonNegative, UnitInterval
    from typing import Annotated

    @verified(
        pre=lambda x: x >= 0,
        post=lambda x, result: result >= x,
    )
    def double(x: float) -> float:
        return x * 2

    assert double.__proof__.verified  # Z3-proven for ALL inputs

Zero-dependency usage (no Z3 required):

    from provably import runtime_checked, NonNegative

    @runtime_checked(pre=lambda x: x >= 0, post=lambda x, r: r >= 0)
    def f(x: float) -> float:
        ...

Install Z3 support:

    pip install 'provably[z3]'
"""

from __future__ import annotations

__version__ = "0.1.0"

from .decorators import verified, VerificationError, runtime_checked, ContractViolationError
from .engine import (
    ProofCertificate,
    Status,
    verify_function,
    verify_module,
    clear_cache,
    configure,
)
from .translator import TranslationError, HAS_Z3
from .types import (
    Gt,
    Ge,
    Lt,
    Le,
    Between,
    NotEq,
    Positive,
    NonNegative,
    UnitInterval,
)

# Re-export Z3 logical combinators for use in pre/post lambdas.
# When Z3 is not installed, each function raises an informative error
# that suggests the correct install command.
if HAS_Z3:
    from z3 import And, Or, Not, Implies
else:

    def And(*args):  # type: ignore[misc]
        raise RuntimeError(
            "z3-solver is not installed. "
            "Run: pip install 'provably[z3]'"
        )

    def Or(*args):  # type: ignore[misc]
        raise RuntimeError(
            "z3-solver is not installed. "
            "Run: pip install 'provably[z3]'"
        )

    def Not(x):  # type: ignore[misc]
        raise RuntimeError(
            "z3-solver is not installed. "
            "Run: pip install 'provably[z3]'"
        )

    def Implies(a, b):  # type: ignore[misc]
        raise RuntimeError(
            "z3-solver is not installed. "
            "Run: pip install 'provably[z3]'"
        )


__all__ = [
    # Decorators
    "verified",
    "runtime_checked",
    # Errors
    "VerificationError",
    "ContractViolationError",
    "TranslationError",
    # Engine
    "verify_function",
    "verify_module",
    "ProofCertificate",
    "Status",
    "clear_cache",
    "configure",
    # Refinement markers
    "Gt",
    "Ge",
    "Lt",
    "Le",
    "Between",
    "NotEq",
    # Convenience aliases
    "Positive",
    "NonNegative",
    "UnitInterval",
    # Z3 combinators (for pre/post lambdas)
    "And",
    "Or",
    "Not",
    "Implies",
    # Metadata
    "HAS_Z3",
    "__version__",
]
