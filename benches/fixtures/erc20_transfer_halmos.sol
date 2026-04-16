// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title ERC-20 Transfer — halmos symbolic test fixture
/// @notice halmos runs this as a symbolic test: all inputs are symbolic,
///         the check() function is the property under verification.
contract ERC20TransferHalmos {
    /// @notice Symbolic proof: transfer(balance, value) is safe when value <= balance.
    ///         halmos exhaustively checks all uint256 inputs satisfying the precondition.
    function check_transfer_no_underflow(uint256 balance, uint256 value) public pure {
        // precondition
        if (value > balance) return;

        uint256 result = balance - value;

        // postconditions
        assert(result == balance - value);
        assert(result <= balance);
    }
}
