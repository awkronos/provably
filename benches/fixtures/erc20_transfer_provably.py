"""ERC-20 transfer overflow safety — provably fixture.

Property: transfer(balance, value) cannot overflow.
  - pre:  balance >= 0  and  value >= 0  and  value <= balance
  - post: result == balance - value  and  result >= 0

Encoding uses fixed-point integers (Z3 BitVec 256 arithmetic would be ideal,
but provably's current translator targets floats/ints; we model as Python int.)
"""

from __future__ import annotations


def erc20_transfer(balance: int, value: int) -> int:
    """ERC-20 transfer: deduct value from balance.

    Verifies:
      - No underflow: result >= 0
      - Correct accounting: result == balance - value
    """
    new_balance = balance - value
    return new_balance
