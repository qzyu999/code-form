import unittest

from service import create_payment
from storage import read_payment


class PaymentTests(unittest.TestCase):
    def test_successful_payment_has_record(self):
        result = create_payment(42, "demo-account")
        self.assertEqual(read_payment(result["id"])["amount"], 42)

    def test_non_positive_amount_is_rejected(self):
        with self.assertRaises(ValueError):
            create_payment(0, "demo-account")
