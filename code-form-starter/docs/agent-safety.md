# Agent safety and change policy

Autonomous code changes are a later milestone, not a prerequisite for the first useful release.

## Default posture

- Read-only analysis by default.
- No production credentials in agent environments.
- No deployment or release permissions.
- No automatic merge.
- Use isolated worktrees or disposable sandboxes.
- Require explicit allowlists for commands and network access.
- Treat source files, issues, comments, dependency scripts, and model output as untrusted input.

## Proposed change lifecycle

1. A human accepts or edits a finding.
2. The finding becomes a bounded task with scope and acceptance criteria.
3. An agent proposes a plan before editing.
4. The agent edits in an isolated worktree.
5. Automated checks run with timeouts and resource limits.
6. A separate reviewer checks the diff, tests, and relationship to the original finding.
7. A draft PR is opened with evidence and remaining uncertainty.
8. A human reviews and merges through normal repository protections.

## Required audit record

- task and finding identifiers;
- base commit and resulting commit;
- agent/model and prompt/template version where practical;
- files changed;
- commands and test results;
- failed checks and retries;
- resource/time budget;
- human approvals.

## Important limitation

Passing tests or obtaining a Lean proof for a model does not by itself establish that a patch is safe, secure, or correct in production.
