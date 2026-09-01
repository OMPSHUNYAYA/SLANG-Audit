# SLANG-Audit v2.4.0 Scientific and Operational Boundaries

## What the reference model establishes

Within the declared bounded structural contract, the repository demonstrates:

- deterministic Boolean audit closure;
- target-specific verdict resolution;
- canonical structural identities;
- semantic verification resistant to simple rehashed-result forgery;
- exact bounded minimal sufficient witnesses;
- exact bounded criticality and counterfactual analysis;
- incremental evidence/rule state transitions with full-recomputation equivalence;
- predecessor-bound proof ledgers, checkpoints, and branch comparison.

## What it does not establish

The reference model does not establish:

```text
external truth
external source provenance
source authenticity
professional audit sufficiency
accounting correctness
legal correctness
regulatory compliance
audit opinion authority
institutional endorsement
trusted timestamps
cryptographic signatures
identity authentication
production certification
```

## Replay and reconciliation

The architecture can resolve a target from an already declared structure without replaying an external transaction history or independently reconciling an external source.

That structural property does not imply:

```text
replay is unnecessary in real-world auditing
reconciliation is unnecessary in real-world auditing
verification is unnecessary in real-world auditing
```

Those procedures may be essential to establish the reliability of the declarations supplied to the structural resolver.

## Evidence commitments

Evidence commitment strings inside the core resolver are identity-binding declarations only.

A separate optional content-binding utility can check whether exact supplied file bytes match a declared SHA-256 commitment. That check establishes byte-to-commitment equality only and does not change the external-truth or provenance boundary.

They do not establish that:

- the committed source exists externally;
- the source was acquired before a target event;
- the source is authentic;
- the source is complete;
- the source is legally admissible;
- the source was independently witnessed.

## Proof ledgers and checkpoints

A ledger can establish internal structural lineage consistency.

A previously pinned checkpoint can distinguish the committed lineage from a different rebuilt lineage.

Neither object proves external chronology unless an external trusted system separately authenticates or timestamps the checkpoint.

## Deployment boundary

The reference implementation is a structural research and verification artifact. Regulated, financial, safety-critical, legal, compliance, or assurance deployments require independent engineering, security review, domain validation, governance, source authentication, professional judgment, and applicable regulatory controls.
