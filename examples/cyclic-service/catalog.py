"""Catalog owns products and delegates quoting."""

from pricing import quote

_products = {"demo": {"price": 20, "stock": 3}}


def get_product(product_id):
    return _products[product_id]


def product_quote(product_id):
    return quote(product_id)


def remove_product(product_id):
    del _products[product_id]
