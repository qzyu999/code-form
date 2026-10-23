import unittest

from workflow import is_terminal, transition


class WorkflowTests(unittest.TestCase):
    def test_order_can_be_paid_and_shipped(self):
        self.assertEqual(transition(transition("pending", "pay"), "ship"), "shipped")

    def test_shipped_is_terminal(self):
        self.assertTrue(is_terminal("shipped"))

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(ValueError):
            transition("pending", "ship")
