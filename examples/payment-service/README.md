# Payment service

A deliberately small payment API with an in-memory persistence boundary.
It demonstrates route discovery, direct test references, a failure handler,
and an explicit documentation contract that the implementation lacks.

API: POST /payments
API: GET /payments/{payment_id}
API: POST /refunds

Expected behavior: a successful payment returns a stored transaction ID.
The storage is only in memory; durable persistence is an open requirement.

Run the example tests from this directory:

```powershell
python -m unittest discover -s tests
```
