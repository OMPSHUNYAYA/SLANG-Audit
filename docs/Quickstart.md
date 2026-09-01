# SLANG-Audit v2.4.0 Quickstart

## Requirements

Core resolver:

```text
Python 3.9+
external Python packages: none
network access: not required
```

Full cross-language verification:

```text
Python 3.9+
Node.js 18+
external Python packages: none
external Node packages: none
network access: not required
```

## 1. Run the core self-test

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --self-test
```

Expected:

```text
SLANG-Audit v2.4.0 self-test
TOTAL 166/166 PASS
```

## 2. Run the demo

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --demo
```

Principal expected lines:

```text
scope:DECLARED_STRUCTURE_ONLY_NOT_AUDIT_OPINION
state:RESOLVED
verification:PASS
proof_ledger_entries:4
proof_ledger_verification:PASS
checkpoint_verification:PASS
external_truth_verified:false
external_source_provenance_verified:false
audit_opinion_authority:NONE
```

## 3. Resolve an editable example

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --resolve examples/SLANG_Audit_Demo_Input_v2_4_0.json --pretty > resolved_bundle.json
```

The structural-scope note is written to standard error so standard output remains valid JSON.

Verify with Python:

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --verify resolved_bundle.json
```

Verify independently with JavaScript:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-bundle resolved_bundle.json
```

Both should return:

```text
PASS
```

## 4. Run proof-ledger validation

```text
python -B validation/SLANG_Audit_Proof_Ledger_Validation_v1_0_0.py --self-test
python -B validation/SLANG_Audit_Proof_Ledger_Validation_v1_0_0.py --run
```

Expected self-test result:

```text
TOTAL 50/50 PASS
```

Expected run result:

```text
proof_ledger_test:PASS
```

## 5. Rebuild the frozen proof ledger

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --ledger validation/SLANG_Audit_Proof_Ledger_Demo_Genesis_Bundle_v2_4_0.json validation/SLANG_Audit_Proof_Ledger_Demo_Delta_Sequence_v1_0_0.json --pretty > proof_ledger.json
```

Verify lineage integrity with Python:

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --verify-ledger proof_ledger.json
```

Verify the pinned checkpoint with Python:

```text
python -B core/SLANG_Audit_Reference_Resolver_v2_4_0.py --verify-ledger-checkpoint proof_ledger.json validation/SLANG_Audit_Proof_Ledger_Demo_Checkpoint_v1_0_0.json
```

Verify the same objects with JavaScript:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-ledger proof_ledger.json
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-ledger-checkpoint proof_ledger.json validation/SLANG_Audit_Proof_Ledger_Demo_Checkpoint_v1_0_0.json
```

All four verification commands should return:

```text
PASS
```

## 6. Run the cross-language conformance gate

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --self-test
python -B validation/SLANG_Audit_Cross_Language_Conformance_Gate_v1_0_0.py --self-test
python -B validation/SLANG_Audit_Cross_Language_Conformance_Gate_v1_0_0.py --run
```

Expected gate result:

```text
TOTAL 39/39 PASS
```

## 7. Optional evidence byte-to-commitment verification

Self-test:

```text
python -B validation/SLANG_Audit_Evidence_Content_Binding_Verifier_v1_0_0.py --self-test
```

Verify exact file bytes against a declared commitment:

```text
python -B validation/SLANG_Audit_Evidence_Content_Binding_Verifier_v1_0_0.py --file evidence.bin --commitment sha256:<digest>
```

A successful byte match returns:

```text
CONTENT_BINDING_PASS
external_truth_verified:false
external_source_provenance_verified:false
```

## 8. Run the package gate

```text
python -B validation/SLANG_Audit_Package_Verifier_v2_4_0.py --self-test
python -B validation/SLANG_Audit_Package_Verifier_v2_4_0.py --verify
```

## Interpretation

Successful reproduction establishes deterministic behavior under the bundled declared structural contract and cross-language verification surface.

It does not authenticate external audit evidence, establish source provenance, prove trusted chronology, or create audit-opinion authority.
