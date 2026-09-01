# SLANG-Audit v2.4.0 Proof Ledger and Checkpoints

## Declared audit lineage

A proof ledger chains certified structural states:

```text
S0 + D1 -> S1
S1 + D2 -> S2
S2 + D3 -> S3
...
```

Every entry binds its predecessor, base bundle, delta, incremental certificate, updated bundle, and target transitions.

## Lineage root

The ordered entry identities produce a deterministic lineage root.

Changing deletion, insertion, substitution, or order changes the lineage structure or causes semantic verification failure.

## Pinned checkpoint

A checkpoint binds:

```text
genesis bundle identity
genesis structure identity
entry count
lineage root identity
last entry identity
terminal bundle identity
terminal structure identity
terminal certificate identity
terminal target-proof identities
```

A checkpoint has its own deterministic identity.

## Internal validity versus committed-history identity

Two different histories may both be internally valid.

They may even reach the exact same terminal bundle.

Therefore:

```text
same terminal state != same history
```

Internal ledger verification establishes structural self-consistency.

Comparison with a previously pinned checkpoint establishes whether the ledger is the same committed structural lineage.

## Branch comparison

The resolver compares ledgers using:

```text
SAME_LINEAGE
PREFIX_EXTENSION
BRANCH_DETECTED
DIFFERENT_GENESIS
```

For a branch, the comparison identifies the common-prefix entry count and branch-point bundle when available.

## Security and authority boundary

A checkpoint is not:

```text
a digital signature
a trusted timestamp
a blockchain consensus proof
an external publication receipt
a professional audit attestation
```

An externally authenticated system could later sign or publish checkpoint identities, but that function is outside v2.4.0.
