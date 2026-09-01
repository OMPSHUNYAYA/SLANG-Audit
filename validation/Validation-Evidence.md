# SLANG-Audit v2.4.0 Validation Evidence

## Core self-test

```text
SLANG-Audit v2.4.0 self-test
TOTAL 166/166 PASS
```

## Proof-ledger validation

```text
SLANG-Audit Proof Ledger Validation v1.0.0 self-test
entries:4
TOTAL 50/50 PASS
```

The proof-ledger validation covers:

- valid ledger verification;
- pinned checkpoint verification;
- exact four-step transition reproduction;
- fresh step-by-step terminal recomputation equality;
- deletion rejection;
- reordering rejection;
- structurally valid delta substitution rejection;
- rehashed transition-forgery rejection;
- terminal certificate tamper rejection;
- an alternative internally valid history that reaches the exact same terminal bundle;
- rejection of that alternative history against the original pinned checkpoint;
- branch detection at genesis;
- branch detection after a common prefix;
- prefix-extension classification;
- same-lineage classification;
- different-genesis classification;
- checkpoint-object integrity versus original-checkpoint identity distinction;
- explicit external truth, provenance, and audit-authority boundaries.

Machine-readable report:

[`SLANG_Audit_Proof_Ledger_Validation_Report_v1_0_0.json`](./SLANG_Audit_Proof_Ledger_Validation_Report_v1_0_0.json)

## Separately implemented JavaScript verifier

The package includes a separately implemented JavaScript verifier that does not import or invoke the Python resolver.

Self-test:

```text
SLANG-Audit JavaScript standalone verifier v1.0.0 self-test
TOTAL 4/4 PASS
```

The JavaScript verifier independently checks the released v2.4.0 semantics for bundles, incremental bundles, proof ledgers, and checkpoints.

## Cross-language conformance

The frozen cross-language gate covers:

```text
10 genuine bundles x 2 verifiers        -> 20 accepts
6 semantic mutations x 2 verifiers      -> 12 rejects
1 incremental bundle x 2 verifiers      -> 2 accepts
1 proof ledger x 2 verifiers             -> 2 accepts
1 checkpointed ledger x 2 verifiers      -> 2 accepts
JavaScript verifier self-test            -> 1 pass
```

Current result:

```text
SLANG-Audit Cross-Language Conformance Gate v1.0.0
TOTAL 39/39 PASS
```

Frozen vectors:

[`conformance/SLANG_Audit_Cross_Language_Conformance_Vectors_v1_0_0.json`](./conformance/SLANG_Audit_Cross_Language_Conformance_Vectors_v1_0_0.json)

## Optional evidence content binding

The separate byte-to-commitment utility self-test returns:

```text
SLANG-Audit Evidence Content-Binding Verifier v1.0.0 self-test
TOTAL 5/5 PASS
```

This utility establishes exact supplied-byte equality with a declared SHA-256 commitment only. It does not establish external truth or provenance.

## Package verification

```text
SLANG-Audit v2.4.0 package verification
TOTAL 104/104 PASS
```

The package gate checks the selected frozen hashes, required repository surface, metadata cleanliness, core validation, proof-ledger validation, JavaScript verification, cross-language conformance, optional content-binding self-test, documented resolve/verify round trips, and deterministic proof-ledger reconstruction.

## Frozen deterministic artifacts

Selected frozen implementation and evidence artifacts are listed in:

[`FROZEN_ARTIFACT_SHA256SUMS_v2_4_0.txt`](./FROZEN_ARTIFACT_SHA256SUMS_v2_4_0.txt)

## Interpretation boundary

The validation establishes deterministic behavior for synthetic declared structures under the released structural semantics and cross-language verification surface.

It does not authenticate external evidence, establish external provenance, prove trusted chronology, or establish professional audit validity.
