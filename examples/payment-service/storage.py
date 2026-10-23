"""In-memory storage is intentionally not durable."""

from itertools import count

_sequence = count(1)
_payments = {}


def insert_payment(amount, account):
    payment_id = str(next(_sequence))
    _payments[payment_id] = {"id": payment_id, "amount": amount, "account": account}
    return payment_id


def read_payment(payment_id):
    return _payments[payment_id]
