// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title ERC-20 Transfer Overflow Safety — solc-SMTChecker fixture
/// @notice Verifies that transfer cannot underflow (uint256 wrapping is a revert in 0.8+)
contract ERC20Transfer {
    mapping(address => uint256) public balanceOf;

    /// @notice Transfer value tokens from sender to recipient.
    /// @dev SMTChecker verifies: balanceOf[sender] decreases by exactly value,
    ///      no underflow (guaranteed by Solidity 0.8 checked arithmetic).
    function transfer(address sender, address recipient, uint256 value) external {
        require(balanceOf[sender] >= value, "ERC20: insufficient balance");
        uint256 senderBalanceBefore = balanceOf[sender];

        balanceOf[sender] -= value;
        balanceOf[recipient] += value;

        // SMTChecker assertion: no underflow
        assert(balanceOf[sender] == senderBalanceBefore - value);
        assert(balanceOf[sender] <= senderBalanceBefore);
    }
}
