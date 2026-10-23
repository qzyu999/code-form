# Verified integer transfer

This example contains two implementations of the same transfer contract.
Both preserve the sum of integer balances, but `transfer_unchecked` accepts
an amount greater than the source balance. `transfer_guarded` rejects it.

In code-form's **Proofs & mathematics** view, run the Lean checker and inspect:

- conservation for both functions;
- nonnegative successful outputs for the guarded function;
- a counterexample to nonnegative outputs for the unchecked function;
- the composed safety theorem and its explicit assumptions;
- axiom dependencies and the exact generated Lean source.

The adapter supports this narrow pure-function shape, not arbitrary Python.
It maps exact built-in integer values to Lean `Int`; runtime type enforcement,
resource exhaustion, concurrency, persistence, and account aliasing are outside
the model. The translator is a stated trusted boundary, not a proved compiler.

Run example tests with the checkout's `.venv` Python:

```powershell
python -m unittest discover -s tests
```
