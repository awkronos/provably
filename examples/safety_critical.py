"""Safety-critical patterns — bounds preservation, safety gates.

Demonstrates provably used the way Kagami uses Z3:
  - Parameter contraction: adaptive parameters stay in a proven safe range
  - Safety gate: motor actions blocked when barrier function h < 0
  - Multiplicative decay/boost with clamped bounds
  - Forward invariance: a step keeps you inside the safe set

These are not toy examples. They are the exact patterns used in a
production GodelLoop to guarantee that no parameter update can push
the system outside its safe operating envelope.
"""

from __future__ import annotations

from provably import verified
from provably.engine import verify_function


# ---------------------------------------------------------------------------
# 1. Parameter contraction — adaptive learning rate stays in [0.5, 5.0]
#
# GodelLoop._enforce_contraction shrinks lr toward a default every step.
# Proven: no matter where lr starts in [0.5, 5.0], it stays there.
# ---------------------------------------------------------------------------

print("=== 1. Parameter contraction (learning rate) ===")


@verified(
    pre=lambda lr: (lr >= 0.5) & (lr <= 5.0),
    post=lambda lr, result: (result >= 0.5) & (result <= 5.0),
)
def contract_lr(lr: float) -> float:
    """Pull lr toward default=2.0 by 5%, then clamp to [0.5, 5.0]."""
    default = 2.0
    decay = 0.05
    new_lr = lr + (default - lr) * decay
    if new_lr < 0.5:
        return 0.5
    elif new_lr > 5.0:
        return 5.0
    else:
        return new_lr


cert = contract_lr.__proof__
print(f"Status: {cert}")
print(f"  Pre:  lr in [0.5, 5.0]")
print(f"  Post: result in [0.5, 5.0]")
print(f"  contract_lr(0.5) = {contract_lr(0.5)}")
print(f"  contract_lr(5.0) = {contract_lr(5.0)}")
print(f"  contract_lr(2.0) = {contract_lr(2.0)}")
print()


# ---------------------------------------------------------------------------
# 2. Safety gate — if h < 0, motor action is ALWAYS blocked
#
# The safety barrier h(x) >= 0 is the primary invariant. When it's violated,
# no motor command should reach the actuators. Proven here: if h < 0, the
# gate function always returns 0 regardless of what action was requested.
# ---------------------------------------------------------------------------

print("=== 2. Safety gate (h < 0 => action blocked) ===")


@verified(
    pre=lambda h, action: h < 0,
    post=lambda h, action, result: result == 0,
)
def safety_gate(h: float, action: int) -> int:
    """Block motor action when safety barrier is violated."""
    if h < 0:
        return 0  # blocked
    return action  # pass-through


cert2 = safety_gate.__proof__
print(f"Status: {cert2}")
print(f"  safety_gate(-0.1, 5) = {safety_gate(-0.1, 5)}  (blocked)")
print(f"  safety_gate(0.5, 5)  = {safety_gate(0.5, 5)}   (allowed)")
print()

# Also prove the safe case: when h >= 0, action passes through unchanged
cert2b = verify_function(
    safety_gate,
    pre=lambda h, action: h >= 0,
    post=lambda h, action, result: result == action,
)
print(f"Safe case (h >= 0 => result == action): {cert2b}")
print()


# ---------------------------------------------------------------------------
# 3. Forward invariance — one step of parameter decay stays in bounds
#
# Proves that multiplicative decay with a floor preserves the invariant.
# This is the discrete analog of the CBF forward-invariance condition.
# ---------------------------------------------------------------------------

print("=== 3. Forward invariance (decay with floor) ===")


@verified(
    pre=lambda x: (x >= 0.1) & (x <= 0.8),
    post=lambda x, result: (result >= 0.1) & (result <= 0.8),
)
def decay_step(x: float) -> float:
    """Apply 5% decay, floor at 0.1.

    Invariant: x in [0.1, 0.8] is forward-invariant under this map.
    """
    new_x = x * 0.95
    if new_x < 0.1:
        return 0.1
    return new_x


cert3 = decay_step.__proof__
print(f"Status: {cert3}")
print(f"  decay_step(0.8) = {decay_step(0.8):.4f}")
print(f"  decay_step(0.1) = {decay_step(0.1):.4f}")
print()


# ---------------------------------------------------------------------------
# 4. Exploration boost with ceiling — boost then clamp
#
# Proves that a multiplicative boost with an upper clamp preserves bounds.
# ---------------------------------------------------------------------------

print("=== 4. Exploration boost with ceiling ===")


@verified(
    pre=lambda x: (x >= 0.5) & (x <= 5.0),
    post=lambda x, result: (result >= 0.5) & (result <= 5.0),
)
def boost_step(x: float) -> float:
    """Boost exploration weight by 50%, ceiling at 5.0."""
    new_x = x * 1.5
    if new_x > 5.0:
        return 5.0
    return new_x


cert4 = boost_step.__proof__
print(f"Status: {cert4}")
print(f"  boost_step(0.5) = {boost_step(0.5):.4f}")
print(f"  boost_step(3.5) = {boost_step(3.5):.4f}")
print()


# ---------------------------------------------------------------------------
# 5. Risk parameter — proven never exceeds maximum risk threshold
#
# Simulates lambda_risk update: pull toward target, clamp to safe range.
# ---------------------------------------------------------------------------

print("=== 5. Risk parameter update ===")


@verified(
    pre=lambda risk: (risk >= 0.05) & (risk <= 0.5),
    post=lambda risk, result: (result >= 0.05) & (result <= 0.5),
)
def update_risk(risk: float) -> float:
    """Update risk multiplier: decay toward 0.1, clamp to [0.05, 0.5]."""
    target = 0.1
    step = 0.02
    new_risk = risk + (target - risk) * step
    if new_risk < 0.05:
        return 0.05
    elif new_risk > 0.5:
        return 0.5
    return new_risk


cert5 = update_risk.__proof__
print(f"Status: {cert5}")
print(f"  update_risk(0.05) = {update_risk(0.05):.4f}")
print(f"  update_risk(0.5)  = {update_risk(0.5):.4f}")
print(f"  update_risk(0.1)  = {update_risk(0.1):.4f}")
print()


# ---------------------------------------------------------------------------
# 6. Composing safety steps — show all invariants hold
# ---------------------------------------------------------------------------

print("=== 6. All safety invariants ===")
all_certs = [
    ("contract_lr", cert),
    ("safety_gate", cert2),
    ("safety_gate (safe case)", cert2b),
    ("decay_step", cert3),
    ("boost_step", cert4),
    ("update_risk", cert5),
]
all_verified = all(c.verified for _, c in all_certs)
for name, c in all_certs:
    status_sym = "Q.E.D." if c.verified else f"FAILED({c.status.value})"
    print(f"  {status_sym:12s}  {name}")
print()
print(f"All invariants proven: {all_verified}")
