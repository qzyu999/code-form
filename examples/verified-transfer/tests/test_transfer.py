import unittest

from transfer import transfer_guarded, transfer_unchecked


class TransferTests(unittest.TestCase):
    def test_counterexample_to_unchecked_nonnegative_output(self):
        self.assertEqual(transfer_unchecked(10, 0, 11), (-1, 11))

    def test_guarded_transfer_rejects_counterexample(self):
        with self.assertRaises(ValueError):
            transfer_guarded(10, 0, 11)

    def test_guarded_transfer_preserves_funds(self):
        self.assertEqual(transfer_guarded(10, 4, 3), (7, 7))
