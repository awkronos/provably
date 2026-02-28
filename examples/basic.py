"""Basic provably usage — your first verified function.

Demonstrates:
  - @verified with a postcondition
  - What a counterexample looks like
  - Accessing the ProofCertificate directly
  - The raise_on_failure=True mode that raises on failure
"""

from __future__ import annotations

from provably import verified, VerificationError, Status
from provably.engine import verify_function


# ---------------------------------------------------------------------------
# 1. A function with a correct postcondition — proof succeeds
# ---------------------------------------------------------------------------

@verified(post=lambda x, result: result >= 0)
def safe_abs(x: float) -> float:
    """Absolute value: always returns a non-negative number."""
    if x >= 0:
        return x
    return -x


print("=== 1. Correct proof ===")
cert = safe_abs.__proof__
print(f"Status:      {cert.status.value}")
print(f"Verified:    {cert.verified}")
print(f"Function:    {cert.function_name}")
print(f"Solver time: {cert.solver_time_ms:.2f}ms")
print(f"Z3 version:  {cert.z3_version}")
print(f"Certificate: {cert}")
print()


# ---------------------------------------------------------------------------
# 2. A function with a wrong postcondition — counterexample returned
# ---------------------------------------------------------------------------

@verified(post=lambda x, result: result > 0)
def negate(x: float) -> float:
    """Negate x. The postcondition 'result > 0' is WRONG."""
    return -x


print("=== 2. Counterexample detected ===")
cert2 = negate.__proof__
print(f"Status:          {cert2.status.value}")
print(f"Counterexample:  {cert2.counterexample}")
# The counterexample shows an x > 0 where -x <= 0
if cert2.counterexample:
    x_val = cert2.counterexample["x"]
    ret_val = cert2.counterexample["__return__"]
    print(f"  x={x_val}  =>  negate(x)={ret_val}  violates result > 0")
print()


# ---------------------------------------------------------------------------
# 3. Accessing the certificate via verify_function (no decorator)
# ---------------------------------------------------------------------------

def clamp(val: float, lo: float, hi: float) -> float:
    """Clamp val to [lo, hi]."""
    if val < lo:
        return lo
    elif val > hi:
        return hi
    else:
        return val


print("=== 3. Direct verify_function call ===")
cert3 = verify_function(
    clamp,
    pre=lambda val, lo, hi: lo <= hi,
    post=lambda val, lo, hi, result: (result >= lo) & (result <= hi),
)
print(f"Status:  {cert3.status.value}")
print(f"Pre:     {cert3.preconditions}")
print(f"Post:    {cert3.postconditions}")
print(cert3)
print()

# Without the precondition — should find a counterexample (lo > hi)
cert3b = verify_function(
    clamp,
    post=lambda val, lo, hi, result: (result >= lo) & (result <= hi),
)
print(f"Without pre: {cert3b.status.value}")
print(f"  Counterexample: {cert3b.counterexample}")
print()


# ---------------------------------------------------------------------------
# 4. raise_on_failure=True raises VerificationError on failure
# ---------------------------------------------------------------------------

print("=== 4. raise_on_failure=True mode ===")
try:
    @verified(raise_on_failure=True, post=lambda x, result: result == x + 2)
    def inc_wrong(x: float) -> float:
        """Off-by-one error: returns x+1, not x+2."""
        return x + 1

    print("ERROR: should have raised!")
except VerificationError as e:
    print(f"VerificationError raised as expected")
    print(f"  Status:          {e.certificate.status.value}")
    print(f"  Counterexample:  {e.certificate.counterexample}")
print()


# ---------------------------------------------------------------------------
# 5. Runtime behavior is unchanged
# ---------------------------------------------------------------------------

print("=== 5. Runtime behavior unchanged ===")
print(f"safe_abs(-7) = {safe_abs(-7)}")
print(f"safe_abs(3)  = {safe_abs(3)}")
print(f"clamp(15, 0, 10) = {clamp(15, 0, 10)}")
print(f"clamp(-5, 0, 10) = {clamp(-5, 0, 10)}")
print(f"clamp(5, 0, 10)  = {clamp(5, 0, 10)}")
