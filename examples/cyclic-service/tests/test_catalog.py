import unittest

from catalog import get_product, product_quote


class CatalogTests(unittest.TestCase):
    def test_product_is_available(self):
        self.assertEqual(get_product("demo")["stock"], 3)

    def test_quote_includes_tax(self):
        self.assertEqual(product_quote("demo"), 22)
