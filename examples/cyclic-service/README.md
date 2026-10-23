# Cyclic service

A small dependency-cycle example: `catalog` imports `pricing`, which
imports `catalog` inside a function. Deferred imports can make a cycle
work at runtime, so the analyzer reports it as a candidate to investigate.

`pricing.quote` catches all exceptions and returns `None`.
`catalog.remove_product` has no direct test reference.

Run:

```powershell
python -m unittest discover -s tests
```
