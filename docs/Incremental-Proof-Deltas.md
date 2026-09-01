# SLANG-Audit v2.4.0 Incremental Proof Deltas

## Purpose

Incremental resolution represents a transition from one certified declared audit state to another.

```text
base certified bundle + declared delta -> updated certified bundle
```

## Supported delta operations

The v2.4.0 incremental profile supports bounded operations over:

```text
evidence add/replace
evidence removal
rule add/replace
rule removal
```

Atom declarations, control definitions, and target-set changes are not incrementally mutated under this profile.

## Base binding

A delta is bound to the exact base bundle identity. A delta created for another base state is refused.

## Dependency propagation

The resolver identifies atoms whose support may change, then propagates that impact through the rule dependency graph to target controls.

It distinguishes:

```text
dependency_impacted_targets
preserved_targets
proof_changed_targets
```

## Target-proof preservation

An unaffected target may retain the same target-local proof identity even though the whole audit bundle changes.

This establishes:

```text
whole audit state changes
!=
every target proof changes
```

## Full-recomputation equivalence

Correctness is guarded by a fresh full recomputation.

An incremental bundle is accepted only when:

```text
incremental updated result == fresh full recomputation result
```

The current reference architecture therefore demonstrates proof isolation and certified state evolution. It does not claim performance superiority over full recomputation.

## History binding

Incremental bundles provide the transition objects used by the proof-ledger layer.
