# SLANG-Audit v2.4.0 Certificate and Verification

## Bundle structure

A resolved bundle binds:

```text
canonical structure
certificate
bundle identity
```

The certificate records target resolution, structural closure, support lineage, target analysis, minimal-witness information when applicable, criticality information when applicable, and explicit authority boundaries.

## Semantic verification

Verification does not merely check whether stored SHA-256 identities match stored content.

Both bundled verification implementations independently recompute the v2.4.0 structural semantics required to validate accepted proof objects.

Therefore:

```text
false conclusion
+ recomputed outer hashes
!=
valid certificate
```

## Two verification implementations

The package contains:

- the Python reference verifier path in [`SLANG_Audit_Reference_Resolver_v2_4_0.py`](../core/SLANG_Audit_Reference_Resolver_v2_4_0.py);
- the separately implemented JavaScript verifier [`SLANG_Audit_Standalone_Verifier_v1_0_0.js`](../validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js).

The JavaScript verifier does not import the Python resolver, invoke Python, or shell out to the producer.

The frozen cross-language gate requires both implementations to accept the genuine vectors and reject the rehashed semantic mutations.

Current result:

```text
TOTAL 39/39 PASS
```

See [Cross-Language Verification](./Cross-Language-Verification.md) and the [Portable Certificate and Ledger Specification](./Portable-Certificate-and-Ledger-Specification.md).

## Deterministic identities

SLANG-Audit uses SHA-256 identities for canonical structures, evidence objects, rules, controls, certificates, bundles, target proofs, witnesses, cuts, deltas, incremental bundles, ledger entries, lineage roots, checkpoints, and proof ledgers.

Canonicalization creates one deterministic serialization for an admitted object. SHA-256 then provides a collision-resistant deterministic identity for that serialization.

No mathematical injectivity claim is made.

A SHA-256 identity does not by itself provide external authorship, authenticity, legal admissibility, or trusted time.

## Evidence commitments

An optional evidence commitment inside the structural resolver has semantics:

```text
IDENTITY_BINDING_ONLY
```

Changing the commitment changes the structural identity even when the logical claims remain the same.

```text
same declared logical claims + different evidence commitment
-> potentially same verdict
-> different structure identity
```

A separate optional utility can additionally check whether exact supplied file bytes match a declared SHA-256 commitment. See [Evidence Content Binding](./Evidence-Content-Binding.md).

That check still does not establish source provenance or truth.

## Python verification commands

Verify a normal bundle:

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --verify bundle.json
```

Verify an incremental bundle:

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --verify-incremental incremental_bundle.json
```

Verify a proof ledger:

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --verify-ledger proof_ledger.json
```

Verify against a checkpoint:

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --verify-ledger-checkpoint proof_ledger.json checkpoint.json
```

## JavaScript verification commands

Self-test:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --self-test
```

Verify a normal bundle:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-bundle bundle.json
```

Verify an incremental bundle:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-incremental incremental_bundle.json
```

Verify a proof ledger:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-ledger proof_ledger.json
```

Verify against a checkpoint:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-ledger-checkpoint proof_ledger.json checkpoint.json
```

## Authority boundary

A verified structural certificate means that the declared structure and proof object agree under the released v2.4.0 semantics.

It does not mean that an external auditor, institution, regulator, accountant, security authority, data owner, or evidence custodian has endorsed the content.
