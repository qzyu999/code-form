# Verified terminal-state invariant

A repaired version of the order workflow with no transition out of a terminal
state. In **Proofs & mathematics**, Lean checks one-step preservation and then
uses induction to prove that every finite event sequence preserves a terminal
state. This is unbounded over sequence length, not a fixed-depth simulation.

Unlisted state/event pairs are identity transitions in the mathematical model.
The runtime function rejects them; this source/model boundary remains visible.
