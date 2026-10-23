"""Two pure implementations of a reviewed integer-balance contract."""


def transfer_unchecked(source: int, destination: int, amount: int):
    """Faulty: a positive amount can exceed the available balance."""
    if amount <= 0:
        raise ValueError("Amount must be positive")
    return source - amount, destination + amount


def transfer_guarded(source: int, destination: int, amount: int):
    """Proposed repair: reject overdrafts before returning new balances."""
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if amount > source:
        raise ValueError("Insufficient funds")
    return source - amount, destination + amount
