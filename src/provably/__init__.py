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

from __future__ import annotations

__version__ = "0.2.1"

from z3 import And, Implies, Not, Or

from .decorators import ContractViolationError, VerificationError, runtime_checked, verified
from .engine import (
    ProofCertificate,
    Status,
    clear_cache,
    configure,
    verify_function,
    verify_module,
)
from .translator import TranslationError
from .types import (
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

__all__ = [
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
    "__version__",
]
