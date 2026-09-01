# SLANG-Audit v2.4.0 Portable Certificate and Ledger Specification

## 1. Purpose

This document describes the portable machine-readable verification surface used by SLANG-Audit v2.4.0.

It is intended to let an independent implementation verify SLANG-Audit objects without importing or calling the producer resolver.

The specification covers:

- canonical JSON and deterministic identities;
- canonical audit structures;
- target certificates and proof objects;
- minimal-witness and counterfactual objects;
- incremental deltas and delta certificates;
- predecessor-bound proof ledgers;
- checkpoints and lineage roots.

The scope is declared structural verification only.

```text
external_truth_verified:false
external_source_provenance_verified:false
audit_opinion_authority:NONE
```

---

## 2. Canonical JSON

Identity-bearing objects use deterministic JSON serialization with these rules:

- object keys are sorted lexicographically;
- separators are exactly `,` and `:` with no added spaces;
- strings are JSON escaped and represented in ASCII-compatible form;
- Booleans are `true` or `false`;
- `null` is represented as `null`;
- binary floating-point values are outside the admitted structural input contract;
- non-finite numeric values are refused;
- duplicate JSON object keys are refused by the strict input loaders.

The conceptual identity relation is:

```text
object
-> canonical JSON bytes
-> SHA-256
-> prefixed deterministic identity
```

For an identity prefix `P` and object `X`:

```text
identity(P, X) = P + ":" + SHA256(canonical_json(X))
```

SHA-256 is used as a collision-resistant deterministic identity mechanism. No mathematical injectivity claim is made.

---

## 3. Canonical Structure

Canonical structures use:

```text
schema: SLANG-AUDIT-CANONICAL-1
source_schema: SLANG-AUDIT-STRUCTURE-2
profile_id: SLANG-AUDIT-DECLARED-EVIDENCE-1
canonicalization_id: SLANG-AUDIT-CANONICAL-BOOLEAN-1
```

A canonical structure contains:

- sorted atom identifiers;
- sorted target-control identifiers;
- canonical evidence objects;
- canonical structural rules;
- canonical control definitions;
- deterministic evidence identities;
- deterministic rule identities;
- deterministic control identities;
- one canonical structure identity.

Evidence objects have:

```text
id
claims
commitment
```

An optional evidence commitment has the form:

```text
sha256:<64 lowercase hexadecimal digits>
```

Inside the core structural resolver, that commitment has identity-binding semantics only.

Rules have:

```text
id
if_all
then
```

`then` contains exactly one Boolean conclusion literal.

Controls have:

```text
id
require
```

Each target names one declared control.

---

## 4. Structural Closure and Target Verdicts

Evidence claims seed Boolean literal support.

Rules fire only when every required premise literal is supported and its opposite is not supported.

The target verdict contract is:

```text
PASS | VIOLATED | INCOMPLETE | ABSTAIN
```

The resolver-state contract is:

```text
RESOLVED | INCOMPLETE | ABSTAIN | FORBIDDEN | UNSUPPORTED
```

Target semantics are:

```text
PASS
= every required target literal is supported and unopposed

VIOLATED
= at least one required target literal has unambiguous opposing support

INCOMPLETE
= at least one required target literal lacks both required and opposing support

ABSTAIN
= at least one required target literal has both required and opposing support
```

A `VIOLATED` target can occur within resolver state `RESOLVED` because the target has been structurally determined.

---

## 5. Bundle and Certificate

Normal bundles use:

```text
schema: SLANG-AUDIT-BUNDLE-6
version: 2.4.0
```

A bundle contains:

```text
canonical_structure
certificate
bundle_id
```

The certificate uses:

```text
schema: SLANG-AUDIT-CERTIFICATE-6
version: 2.4.0
```

It binds:

- the canonical structure identity;
- resolver state and reason codes;
- per-target verdicts and witnesses;
- the structural closure;
- target-specific analysis;
- target-local proof identities;
- explicit authority boundaries.

Certificate verification requires semantic recomputation from the canonical structure, not only outer hash matching.

```text
hash consistency != semantic proof validity
```

---

## 6. Minimal Witnesses and Criticality

For structurally decidable targets, the certificate may include a canonical minimal sufficient witness.

The optimization order is:

```text
minimum evidence_count + rule_count
-> minimum evidence_count
-> minimum rule_count
-> canonical lexical tie-break
```

The witness includes:

- target and verdict;
- decisive literals;
- selected evidence sources and identities;
- selected rules and identities;
- derivation paths;
- restricted witness-structure identity;
- witness identity.

Counterfactual analysis can include:

```text
minimal_verdict_cut
completion_frontier
minimal_repair_to_pass
```

These objects are structural counterfactuals inside the admitted model. They are not professional audit recommendations.

---

## 7. Incremental Delta Format

Incremental deltas use:

```text
schema: SLANG-AUDIT-DELTA-1
```

A delta is bound to an exact base bundle and may contain:

```text
remove_evidence
upsert_evidence
remove_rules
upsert_rules
```

The delta identity binds:

```text
base_bundle_id
+ normalized delta operations
```

An incremental bundle uses:

```text
schema: SLANG-AUDIT-INCREMENTAL-BUNDLE-1
```

and contains:

```text
base_bundle
delta
delta_certificate
updated_bundle
incremental_bundle_id
```

The delta certificate records:

- affected atoms;
- dependency-impacted targets;
- proof-changed targets;
- preserved targets;
- per-target transitions;
- recomputed target-proof identities;
- preserved target-proof identities;
- full-recomputation equivalence.

Accepted incremental output must satisfy:

```text
incremental updated result == fresh full recomputation result
```

---

## 8. Proof Ledger

Proof ledgers use:

```text
schema: SLANG-AUDIT-PROOF-LEDGER-1
version: 2.4.0
```

A ledger contains:

```text
genesis_bundle
entries
terminal_bundle
checkpoint
ledger_id
```

Each entry binds:

```text
index
predecessor_entry_id
base_bundle_id
base_structure_id
delta
delta_id
delta_certificate_id
incremental_bundle_id
updated_bundle_id
updated_structure_id
dependency_impacted_targets
proof_changed_targets
preserved_targets
transitions
entry_id
```

For entry `n`:

```text
entry_n
= H(predecessor_entry_id, base state, delta, resulting state, transition metadata)
```

The lineage root binds the genesis bundle identity and ordered entry identities.

---

## 9. Checkpoint

Checkpoints use:

```text
schema: SLANG-AUDIT-LEDGER-CHECKPOINT-1
version: 2.4.0
```

A checkpoint binds:

- genesis bundle and structure identities;
- entry count;
- lineage root;
- last entry identity;
- terminal bundle, structure, and certificate identities;
- terminal target-proof identities;
- explicit external-authority boundaries.

A checkpoint is a deterministic structural commitment.

```text
checkpoint != digital signature
checkpoint != trusted timestamp
checkpoint != external publication proof
```

See [External Checkpoint Anchoring](./External-Checkpoint-Anchoring.md) for optional external trust-layer patterns.

---

## 10. Independent Verification Contract

The package contains two verification implementations:

```text
Python reference verifier
JavaScript standalone verifier
```

The JavaScript verifier does not import the Python resolver and does not invoke Python.

For genuine frozen conformance vectors:

```text
Python -> PASS
JavaScript -> PASS
```

For the frozen rehashed semantic mutations:

```text
Python -> REJECT
JavaScript -> REJECT
```

See [Cross-Language Verification](./Cross-Language-Verification.md).

---

## 11. Scope Boundary

Portable structural verification establishes consistency under the admitted v2.4.0 structural contract.

It does not establish:

```text
external truth
source provenance
source authenticity
professional audit sufficiency
legal or accounting correctness
trusted chronology
audit opinion authority
```
