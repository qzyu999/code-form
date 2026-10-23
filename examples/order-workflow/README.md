# Order workflow

A finite state machine with a deliberately questionable transition:
`cancelled --reopen→ pending`. `cancelled` is declared terminal.

The analyzer extracts the literal `TRANSITIONS` table and
`TERMINAL_STATES`, checks every transition, and produces a counterexample
and an unchecked Lean model. The current tests pass because they omit the
terminal-state requirement.

Run:

```powershell
python -m unittest discover -s tests
```

For a comparison exercise, remove the `("cancelled", "reopen")` entry,
analyze again, and compare the two snapshots.
