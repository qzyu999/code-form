"""Business rules and persistence coordination."""

from storage import insert_payment, read_payment


def create_payment(amount, account):
    """Validate a positive amount before storing a payment."""
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if not account:
        raise ValueError("Account is required")
    payment_id = insert_payment(amount, account)
    return {"id": payment_id, "status": "success"}


def lookup_payment(payment_id):
    try:
        return read_payment(payment_id)
    except Exception:
        return None
