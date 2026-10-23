"""A minimal decorator registry avoids requiring a web framework."""

from service import create_payment, lookup_payment


class Router:
    def __init__(self):
        self.routes = {}

    def post(self, path):
        def register(handler):
            self.routes[("POST", path)] = handler
            return handler
        return register

    def get(self, path):
        def register(handler):
            self.routes[("GET", path)] = handler
            return handler
        return register


router = Router()


@router.post("/payments")
def pay(amount, account):
    return create_payment(amount, account)


@router.get("/payments/{payment_id}")
def get_payment(payment_id):
    return lookup_payment(payment_id)
