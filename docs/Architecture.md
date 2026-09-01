# SLANG-Audit v2.4.0 Architecture

## Core relation

```text
declared audit evidence + structural rules + controls
-> canonical structure
-> deterministic closure
-> target-specific verdicts
-> proof-carrying certificate
```

The architecture then adds:

```text
target verdict
-> dependency cone
-> minimal sufficient witness
-> minimal verdict cut
-> bounded completion/repair counterfactual

previous certified state + declared delta
-> dependency-scoped target recomputation
-> unaffected target-proof preservation
-> full fresh-recomputation equivalence

ordered certified transitions
-> predecessor-bound proof ledger
-> lineage root
-> checkpoint
-> lineage comparison
```

## Diagram

[View the SLANG-Audit architecture diagram](./SLANG-Audit-Diagram.png).

## Layer 1: declared structure

The input contains:

```text
atoms
targets
evidence
rules
controls
```

Evidence claims and rule literals are Boolean. Evidence may optionally carry a SHA-256 commitment string whose semantics are identity binding only.

## Layer 2: canonicalization

Semantically equivalent declaration ordering is normalized before structural identity calculation.

The canonical structure identity binds the declared structure, not the implementation file or proof-system version.

## Layer 3: closure and target resolution

The resolver computes bounded fixed-point closure. Rules do not fire from contradictory premises.

Each target is resolved independently against its declared control requirements.

```text
all required literals supported -> PASS
unambiguous opposite supported  -> VIOLATED
required support unavailable    -> INCOMPLETE
required literal contradictory  -> ABSTAIN
```

## Layer 4: explanation and criticality

For non-incomplete targets, exact bounded witness search identifies a canonical minimal sufficient declared substructure.

Counterfactual analysis searches for exact bounded minimum changes under the declared resource limits.

## Layer 5: incremental evolution

A delta is bound to its base certified bundle. The incremental path identifies dependency-impacted targets and recomputes target proofs. Acceptance requires equality with a fresh full recomputation.

## Layer 6: proof ledger

A proof ledger binds each transition to its predecessor and resulting state. The ledger carries a lineage root and checkpoint.

A checkpoint can distinguish a previously committed lineage from another internally valid history, including a history that reaches the same terminal bundle.

## Authority boundary

```text
external_truth_verified:false
external_source_provenance_verified:false
audit_opinion_authority:NONE
```

The architecture is a structural reasoning and integrity model, not a professional audit authority or external evidence-authentication system.
