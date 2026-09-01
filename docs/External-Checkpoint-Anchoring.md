# SLANG-Audit v2.4.0 External Checkpoint Anchoring

## Core checkpoint semantics

SLANG-Audit checkpoints are deterministic structural commitments to a declared proof-ledger lineage.

They do not themselves provide:

```text
a digital signature
a trusted timestamp
an external publication receipt
identity authentication
institutional endorsement
```

## Optional external trust layer

A deployment may independently bind a checkpoint identity to an external trust mechanism.

Conceptually:

```text
SLANG-Audit checkpoint_id
-> external signature and/or trusted timestamp and/or transparency publication
-> externally authenticated anchoring record
```

Possible external patterns include:

- signing the checkpoint identity with an organization-controlled signing key;
- submitting the checkpoint identity to an independently operated trusted timestamp service;
- publishing the checkpoint identity in an append-only transparency system;
- publishing the checkpoint identity in a separately controlled public record.

No specific provider is required or endorsed by the reference implementation.

## Verification separation

The two layers should remain distinct:

```text
SLANG-Audit verifier
-> verifies declared structural lineage and checkpoint identity

external trust verifier
-> verifies signature, timestamp, publication, or transparency evidence
```

This prevents the structural resolver from claiming trust properties supplied by an external system.

## Chronology boundary

Without a separately authenticated external anchor:

```text
valid checkpoint
!=
proof of when the checkpoint existed externally
```

With an external anchor, the strength of the chronology claim depends on the security, governance, and verification properties of that external mechanism.
