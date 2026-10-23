"""Pricing reaches back into catalog through a deferred import."""


def quote(product_id):
    from catalog import get_product

    try:
        product = get_product(product_id)
        return product["price"] * 1.1
    except Exception:
        return None
