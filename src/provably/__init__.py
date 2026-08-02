"""Provably — proof-carrying Python via Z3.

Annotate functions with contracts, get automatic formal proofs.

    from provably import verified
    from typing import Annotated
    from provably.types import Ge

    @verified(
        pre=lambda x: x >= 0,
        post=lambda x, result: result >= x,
    )
    def double(x: float) -> float:
        return x * 2

    assert double.__proof__.verified  # Z3-proven for ALL inputs

ProofCertificate extras
-----------------------
- ``cert.explain()`` — human-readable multi-line description of the result.
- ``cert.to_prompt()`` — single-paragraph LLM-friendly repair message.

Optional extras
---------------
- ``provably.hypothesis`` — Hypothesis bridge (``pip install provably[hypothesis]``).
- ``provably.pytest_plugin`` — pytest ``--provably-report`` and ``proven`` marker
  (auto-registered when provably is installed).
"""

from __future__ import annotations  # pragma: no cover

__version__ = "0.4.0"  # pragma: no cover

from z3 import And, Implies, Not, Or  # pragma: no cover

from .decorators import (
    ContractViolationError,
    VerificationError,
    runtime_checked,
    verified,
)  # pragma: no cover
from .engine import (  # pragma: no cover
    ProofCertificate,
    Status,
    clear_cache,
    configure,
    verify_function,
    verify_module,
)
from .lean4 import HAS_LEAN4, LEAN4_VERSION, export_lean4, verify_with_lean4  # pragma: no cover
from .translator import TranslationError  # pragma: no cover
from .types import (  # pragma: no cover
    Between,
    Ge,
    Gt,
    Le,
    Lt,
    NonNegative,
    NotEq,
    Positive,
    UnitInterval,
)

__all__ = [  # pragma: no cover
    "verified",
    "runtime_checked",
    "VerificationError",
    "ContractViolationError",
    "TranslationError",
    "verify_function",
    "verify_module",
    "ProofCertificate",
    "Status",
    "clear_cache",
    "configure",
    "Gt",
    "Ge",
    "Lt",
    "Le",
    "Between",
    "NotEq",
    "Positive",
    "NonNegative",
    "UnitInterval",
    "And",
    "Or",
    "Not",
    "Implies",
    # Lean4 backend
    "verify_with_lean4",
    "export_lean4",
    "HAS_LEAN4",
    "LEAN4_VERSION",
    "__version__",
]
