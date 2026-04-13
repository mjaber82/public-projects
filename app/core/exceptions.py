class WalletException(Exception):
    """Base exception for wallet-related business logic."""


class InsufficientFundsError(WalletException):
    """Raised when a wallet does not have enough balance for an operation."""

    pass
