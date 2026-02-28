"""Modular verification — verified functions calling verified functions.

When function A calls function B, we can verify A using only B's contract
(pre/post), not B's full implementation. This is the key scalability property
of contract-based formal verification: proof complexity stays local.

Demonstrates:
  - The contracts= parameter for passing verified function contracts
  - How __contract__ is populated by @verified
  - Building a proof dependency chain
  - verify_module() pattern (manual version)
"""

from __future__ import annotations

from typing import Annotated

from provably import verified
from provably.engine import verify_function
from provably.types import Ge, Le, Between

try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


# ---------------------------------------------------------------------------
# 1. Build a verified library of primitives
# ---------------------------------------------------------------------------

print("=== 1. Verified primitive library ===")


@verified(
    pre=lambda x: x >= 0,
    post=lambda x, result: (result >= 0) & (result <= x),
)
def safe_half(x: float) -> float:
    """Halve x. Proven: result in [0, x] when x >= 0."""
    return x / 2


@verified(
    pre=lambda a, b: (a >= 0) & (b >= 0),
    post=lambda a, b, result: (result >= a) & (result >= b),
)
def safe_max(a: float, b: float) -> float:
    """Maximum of two non-negative numbers. Proven: result >= both inputs."""
    if a >= b:
        return a
    return b


@verified(
    pre=lambda x: (x >= 0) & (x <= 1),
    post=lambda x, result: (result >= 0) & (result <= 1),
)
def complement(x: float) -> float:
    """1 - x for x in [0, 1]. Proven: result stays in [0, 1]."""
    return 1.0 - x


for fn in (safe_half, safe_max, complement):
    cert = fn.__proof__
    sym = "Q.E.D." if cert.verified else f"FAIL({cert.status.value})"
    print(f"  {sym:8s}  {cert.function_name}")
print()


# ---------------------------------------------------------------------------
# 2. Inspect the __contract__ attribute
# ---------------------------------------------------------------------------

print("=== 2. __contract__ attribute ===")

c = safe_half.__contract__
print(f"safe_half.__contract__:")
print(f"  verified: {c['verified']}")
print(f"  pre:      {c['pre']}")
print(f"  post:     {c['post']}")
print()


# ---------------------------------------------------------------------------
# 3. Modular verification via contracts= parameter
#
# We verify a function that calls safe_half by passing safe_half's contract.
# The verifier uses only the contract (pre + post), not the implementation.
# ---------------------------------------------------------------------------

print("=== 3. Modular verification with contracts= ===")

if HAS_Z3:
    # Build the contract dict that the engine expects
    safe_half_contract = {
        "pre": safe_half.__contract__["pre"],
        "post": safe_half.__contract__["post"],
        "return_sort": z3.RealSort(),
    }

    def quarter(x: float) -> float:
        """Proven by composition: half(half(x)) when x >= 0."""
        # In the symbolic proof, 'safe_half' is replaced by its contract
        return safe_half(x) / 2

    cert = verify_function(
        quarter,
        pre=lambda x: x >= 0,
        post=lambda x, result: (result >= 0) & (result <= x),
        verified_contracts={"safe_half": safe_half_contract},
    )
    print(f"quarter (via safe_half contract): {cert}")
    print(f"  quarter(8.0) = {quarter(8.0)}")
    print()
else:
    print("  (skipped — z3-solver not installed)")
    print()


# ---------------------------------------------------------------------------
# 4. Proof dependency chain
#
# Show that each proof cites its dependencies.
# ---------------------------------------------------------------------------

print("=== 4. Proof dependency chain ===")

print("Dependency chain:")
print("  safe_half ─────────────────────┐")
print("    post: result in [0, x]        │")
print("                                  ▼")
print("  quarter ──────────────────── uses safe_half contract")
print("    post: result in [0, x]")
print()

proofs = {
    "safe_half": safe_half.__proof__,
    "safe_max": safe_max.__proof__,
    "complement": complement.__proof__,
}
for name, proof in proofs.items():
    status = "proven" if proof.verified else proof.status.value
    print(f"  {name:15s}: {status}  ({proof.solver_time_ms:.1f}ms)")
print()


# ---------------------------------------------------------------------------
# 5. verify_module() — verify all @verified functions in a namespace
#
# Provably does not yet ship a verify_module() helper, but the pattern
# is straightforward: collect all callables with __proof__, report results.
# ---------------------------------------------------------------------------

print("=== 5. verify_module() pattern ===")


def verify_module(namespace: dict) -> dict[str, bool]:
    """Collect and report proof status for all @verified functions in namespace."""
    results: dict[str, bool] = {}
    for name, obj in namespace.items():
        if callable(obj) and hasattr(obj, "__proof__"):
            results[name] = obj.__proof__.verified
    return results


# Simulate a module namespace
module_namespace = {
    "safe_half": safe_half,
    "safe_max": safe_max,
    "complement": complement,
}

results = verify_module(module_namespace)
all_proven = all(results.values())
print(f"Module proof results:")
for name, proven in results.items():
    sym = "Q.E.D." if proven else "FAIL"
    print(f"  {sym:8s}  {name}")
print(f"\nAll functions proven: {all_proven}")
print()


# ---------------------------------------------------------------------------
# 6. A function that is NOT compositionally sound — missing contract
# ---------------------------------------------------------------------------

print("=== 6. Unsound composition (no contract) ===")


def bad_quarter(x: float) -> float:
    """Tries to compose safe_half, but the contract is not passed to verifier."""
    return safe_half(x) / 2


cert_bad = verify_function(
    bad_quarter,
    pre=lambda x: x >= 0,
    post=lambda x, result: result >= 0,
    # NOT passing verified_contracts — the verifier doesn't know about safe_half
)
print(f"bad_quarter (no contract): {cert_bad.status.value}")
if cert_bad.status.value == "translation_error":
    print(f"  Error: {cert_bad.message}")
print(f"  (Expected TRANSLATION_ERROR — 'safe_half' unknown to verifier)")
print()


# ---------------------------------------------------------------------------
# 7. Refinement type composition — annotations as contracts
# ---------------------------------------------------------------------------

print("=== 7. Refinement type composition ===")


@verified
def unit_to_percent(
    x: Annotated[float, Between(0, 1)],
) -> Annotated[float, Between(0, 100)]:
    """Convert unit value to percentage. Both bounds auto-proven from types."""
    return x * 100


@verified
def percent_to_unit(
    pct: Annotated[float, Between(0, 100)],
) -> Annotated[float, Between(0, 1)]:
    """Convert percentage to unit. Round-trip proof."""
    return pct / 100


print(f"unit_to_percent:  {unit_to_percent.__proof__}")
print(f"percent_to_unit:  {percent_to_unit.__proof__}")
print(f"  unit_to_percent(0.75) = {unit_to_percent(0.75)}")
print(f"  percent_to_unit(75.0) = {percent_to_unit(75.0)}")
