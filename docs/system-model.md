# System model

The first release implements schema version `1.0.0` in
[bundle.schema.json](../schemas/bundle.schema.json), with the existing claim
schema reused unchanged. See [architecture.md](architecture.md) for adapter
semantics and [testing.md](testing.md) for inspecting actual bundles.

## Purpose

Represent what a repository contains, what the software appears to do, which claims are supported by evidence, and where uncertainty remains.

The model should be a durable artifact, not just a transient prompt or a set of diagrams.

## Core entities

### Repository snapshot
- repository identifier
- commit SHA
- analyzer version
- language/toolchain versions
- analysis timestamp
- configuration and scope

The deterministic bundle stores captured source text and hashes. Persistence
records `created_at` outside the bundle. The Git baseline and dirty flag are
distinct from the exact captured-content identity.

### Component
A module, package, service, process, subsystem, or other named unit.

### Relationship
A typed, directed relationship such as imports, calls, publishes, subscribes, reads, writes, owns, implements, or depends on.

### Claim
A proposition about the system. Each claim has a statement, epistemic status, evidence, scope, and optional confidence estimate.

Suggested statuses:
- `observed`: directly extracted from code/configuration.
- `inferred`: best-effort interpretation of evidence.
- `proposed`: desired behavior or design recommendation.
- `tested`: supported by a named test under specified conditions.
- `proved`: a proof checker accepted a formal proof of a specified proposition.
- `contradicted`: available evidence conflicts with the claim.
- `unknown`: insufficient evidence.

These statuses are not a simple linear confidence scale. For example, a claim can be tested but not proved.

### Evidence
A source reference, test result, command output, configuration entry, commit, or external specification. Source references should be anchored to a repository revision so later changes do not silently invalidate them.

### Assumption
A condition accepted for analysis but not yet established. Assumptions should have an owner or rationale when possible.

### Invariant
A property intended to hold across a defined boundary, state, or set of operations.

### Finding
A potential issue, risk, missing test, inconsistency, or improvement opportunity. A finding should include evidence, impact, uncertainty, and a suggested validation step.

### Formal artifact
A Lean source file, theorem/proposition identifier, build result, toolchain version, and the exact model/assumptions it depends on.

## Example

For a payment service, a claim might be:

> Every successful payment response has a durable transaction record.

This should not be marked `proved` just because an LLM says it is true. A reasonable workflow is:

1. Locate the handler, persistence boundary, transaction logic, and relevant tests.
2. Mark the initial claim as `inferred`.
3. Check failure paths and transaction semantics.
4. Write a test for relevant scenarios.
5. If the behavior is critical, define an abstract state machine and prove a property of that model.
6. Separately validate that the implementation conforms to the model.

## Evidence and trust

Every generated claim should answer:
- What exact proposition is being asserted?
- Which repository revision does it describe?
- What evidence supports it?
- What evidence might contradict it?
- Is it a fact, interpretation, requirement, test result, or proof?
- What would change the conclusion?

## Lean boundary

Lean should be introduced where formalization adds value, such as:
- state-machine transition invariants;
- authorization policy properties;
- accounting conservation rules;
- protocol safety properties;
- parsers or transformations with tractable semantics.

A proof establishes a theorem under its definitions and assumptions. It does not automatically establish that production source code implements those definitions. That bridge needs its own argument, tests, extraction strategy, or refinement proof.
